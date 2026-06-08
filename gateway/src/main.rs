//! API Gateway — Rust / Actix-web
//!
//! Sits on :8080, proxies to the Python Flask backend on :5000.
//! Responsibilities:
//!   1. JWT authentication on every protected route
//!   2. Per-IP rate limiting (token-bucket via `governor`)
//!   3. Request-ID injection & structured tracing
//!   4. CORS enforcement
//!   5. Upstream error normalisation
//!
//! NOT a responsibility of the Gateway:
//!   - Business logic
//!   - ML / NLP inference
//!   - Database access

use std::{num::NonZeroU32, sync::Arc, time::Duration};

use actix_cors::Cors;
use actix_web::{
    middleware::Logger, web, App, HttpRequest, HttpResponse, HttpServer,
};
use reqwest::Client;
use dashmap::DashMap;
use dotenvy::dotenv;
use governor::{
    clock::DefaultClock,
    state::{InMemoryState, NotKeyed},
    Quota, RateLimiter,
};
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use serde::{Deserialize, Serialize};
use tracing::{error, info, warn};
use uuid::Uuid;

// ─────────────────────────────────────────────
// Config (read once from env at startup)
// ─────────────────────────────────────────────

#[derive(Clone, Debug)]
struct Config {
    /// Full base URL of the Flask backend, e.g. "http://127.0.0.1:5000"
    backend_url: String,
    /// HMAC-SHA256 secret used to verify JWTs issued by the auth service
    jwt_secret: String,
    /// Rate-limit: requests per second per IP (token-bucket replenish rate)
    rate_limit_rps: NonZeroU32,
    /// Maximum burst above the replenish rate
    rate_limit_burst: NonZeroU32,
    /// Comma-separated list of allowed CORS origins
    allowed_origins: Vec<String>,
    /// Gateway listen port
    port: u16,
}

impl Config {
    fn from_env() -> Self {
        let backend_url =
            std::env::var("BACKEND_URL").unwrap_or_else(|_| "http://127.0.0.1:5000".into());

        let jwt_secret = std::env::var("JWT_SECRET")
            .expect("JWT_SECRET must be set — refusing to start without it");

        if jwt_secret.len() < 32 {
            panic!("JWT_SECRET is too short (must be ≥ 32 chars)");
        }

        let rate_limit_rps: NonZeroU32 = std::env::var("RATE_LIMIT_RPS")
            .ok()
            .and_then(|v| v.parse().ok())
            .and_then(NonZeroU32::new)
            .unwrap_or(NonZeroU32::new(10).unwrap());

        let rate_limit_burst: NonZeroU32 = std::env::var("RATE_LIMIT_BURST")
            .ok()
            .and_then(|v| v.parse().ok())
            .and_then(NonZeroU32::new)
            .unwrap_or(NonZeroU32::new(20).unwrap());

        let allowed_origins: Vec<String> = std::env::var("ALLOWED_ORIGINS")
            .unwrap_or_else(|_| "http://localhost:3000".into())
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();

        let port: u16 = std::env::var("GATEWAY_PORT")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(8080);

        Self {
            backend_url,
            jwt_secret,
            rate_limit_rps,
            rate_limit_burst,
            allowed_origins,
            port,
        }
    }
}

// ─────────────────────────────────────────────
// JWT claims
// ─────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
struct Claims {
    sub: String, // subject / user_id (string)
    exp: usize,  // expiry (Unix timestamp)
    iat: usize,  // issued-at
    #[serde(default)]
    role: Option<String>,
}

// ─────────────────────────────────────────────
// Shared application state
// ─────────────────────────────────────────────

/// Per-IP rate-limiter map.  Each entry is an independent token-bucket
/// keyed by the client's IP address string.  Entries are evicted after
/// `LIMITER_TTL_SECS` seconds of inactivity to bound memory growth.
type IpLimiter = RateLimiter<NotKeyed, InMemoryState, DefaultClock>;

const LIMITER_TTL_SECS: u64 = 300; // 5 minutes

struct AppState {
    config: Config,
    /// Single shared HTTP client (connection-pooled, Send + Sync)
    http_client: Client,
    /// Per-IP token-bucket limiters
    rate_limiters: Arc<DashMap<String, (IpLimiter, std::time::Instant)>>,
    /// Shared quota definition (one per-IP bucket is built from this)
    quota: Quota,
}

// ─────────────────────────────────────────────
// Error type
// ─────────────────────────────────────────────

#[derive(Debug, Serialize)]
struct GatewayError {
    status: &'static str,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    request_id: Option<String>,
}

impl GatewayError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            status: "error",
            message: message.into(),
            request_id: None,
        }
    }
    fn with_request_id(mut self, id: impl Into<String>) -> Self {
        self.request_id = Some(id.into());
        self
    }
}

impl std::fmt::Display for GatewayError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

/// Extract the Bearer token from the Authorization header.
fn extract_bearer(req: &HttpRequest) -> Option<&str> {
    req.headers()
        .get("Authorization")?
        .to_str()
        .ok()?
        .strip_prefix("Bearer ")
}

/// Validate the JWT and return the decoded claims.
fn validate_jwt(token: &str, secret: &str) -> Result<Claims, &'static str> {
    let key = DecodingKey::from_secret(secret.as_bytes());
    let mut validation = Validation::new(Algorithm::HS256);
    validation.validate_exp = true;

    decode::<Claims>(token, &key, &validation)
        .map(|data| data.claims)
        .map_err(|_| "Invalid or expired token")
}

/// Derive the forwarding URL: strip the `/api` prefix that the gateway owns,
/// then prepend the backend base URL.
///
/// Example:
///   incoming  → GET /api/chatbot/ask
///   forwarded → GET http://127.0.0.1:5000/api/chatbot/ask
fn build_upstream_url(config: &Config, req: &HttpRequest) -> String {
    let path = req.uri().path();
    let query = req
        .uri()
        .query()
        .map(|q| format!("?{q}"))
        .unwrap_or_default();
    format!("{}{path}{query}", config.backend_url)
}

/// Generate a per-request correlation ID injected as `X-Request-ID`.
fn new_request_id() -> String {
    Uuid::new_v4().to_string()
}

// ─────────────────────────────────────────────
// Health probe (unauthenticated)
// ─────────────────────────────────────────────

async fn health() -> HttpResponse {
    HttpResponse::Ok().json(serde_json::json!({
        "status": "ok",
        "service": "api-gateway"
    }))
}

// ─────────────────────────────────────────────
// Core proxy handler
// ─────────────────────────────────────────────

async fn proxy(req: HttpRequest, body: web::Bytes, data: web::Data<AppState>) -> HttpResponse {
    let request_id = new_request_id();

    // ── 1. Per-IP Rate limit ───────────────────────────────────────────────
    let client_ip = req
        .connection_info()
        .realip_remote_addr()
        .unwrap_or("unknown")
        .to_owned();

    let now = std::time::Instant::now();
    {
        let mut entry = data
            .rate_limiters
            .entry(client_ip.clone())
            .or_insert_with(|| (RateLimiter::direct(data.quota), now));
        entry.1 = now; // refresh last-seen timestamp
        if entry.0.check().is_err() {
            warn!(request_id = %request_id, ip = %client_ip, "Rate limit exceeded");
            return HttpResponse::TooManyRequests().json(
                GatewayError::new("Rate limit exceeded. Please retry after a moment.")
                    .with_request_id(&request_id),
            );
        }
    }

    // ── 2. Authentication (skip /health and /api/chatbot/health) ──────────
    let path = req.uri().path();
    let is_health = path == "/health" || path == "/api/chatbot/health";

    let mut claims = None;
    if !is_health {
        let token = match extract_bearer(&req) {
            Some(t) => t,
            None => {
                return HttpResponse::Unauthorized().json(
                    GatewayError::new("Missing Authorization header").with_request_id(&request_id),
                );
            }
        };

        match validate_jwt(token, &data.config.jwt_secret) {
            Ok(c) => {
                claims = Some(c);
            }
            Err(reason) => {
                warn!(request_id = %request_id, reason, "JWT validation failed");
                return HttpResponse::Unauthorized()
                    .json(GatewayError::new(reason).with_request_id(&request_id));
            }
        }
    }

    // ── 3. Build upstream request ──────────────────────────────────────────
    let upstream_url = build_upstream_url(&data.config, &req);
    info!(request_id = %request_id, method = %req.method(), url = %upstream_url, "Forwarding request");

    let method = match reqwest::Method::from_bytes(req.method().as_str().as_bytes()) {
        Ok(m) => m,
        Err(_) => {
            return HttpResponse::BadRequest()
                .json(GatewayError::new("Unsupported HTTP method").with_request_id(&request_id));
        }
    };

    let mut headers = reqwest::header::HeaderMap::new();

    // Forward safe headers from the client (strip hop-by-hop / security headers)
    for (name, value) in req.headers() {
        let lower = name.as_str().to_lowercase();
        if matches!(
            lower.as_str(),
            "connection"
            | "keep-alive"
            | "proxy-authenticate"
            | "proxy-authorization"
            | "te"
            | "trailers"
            | "transfer-encoding"
            | "upgrade"
            // Strip the original Authorization; downstream gets X-User-ID instead
            | "authorization"
            | "host"
            // Prevent client spoofing of gateway metadata headers
            | "x-gateway-secret"
            | "x-user-id"
            | "x-user-role"
        ) {
            continue;
        }
        if let Ok(hval) = reqwest::header::HeaderValue::from_str(&data.config.jwt_secret) {
            headers.insert("X-Gateway-Secret", hval);
        } {
            headers.insert(hname, hval);
        }
    }

    // Inject gateway-side metadata headers
    // SECURITY: never trust X-Forwarded-For from client; set it ourselves.
    // client_ip was captured above (before rate-limit check) so reuse it.
    headers.insert("X-Request-ID", request_id.as_str().parse().unwrap());
    headers.insert("X-Gateway", "rust-actix/1.0".parse().unwrap());
    headers.insert("X-Forwarded-For", client_ip.parse().unwrap());
    if let Ok(hval) = reqwest::header::HeaderValue::from_str(&data.config.jwt_secret) {
        headers.insert("X-Gateway-Secret", hval);
    }

    if let Some(c) = claims {
        if let Ok(hval) = reqwest::header::HeaderValue::from_str(&c.sub) {
            headers.insert("X-User-Id", hval);
        }
        if let Some(role) = c.role {
            if let Ok(hval) = reqwest::header::HeaderValue::from_str(&role) {
                headers.insert("X-User-Role", hval);
            }
        }
    }

    // ── 4. Send to backend ─────────────────────────────────────────────────
    let upstream_result = data
        .http_client
        .request(method, &upstream_url)
        .headers(headers)
        .body(body.to_vec())
        .send()
        .await;

    match upstream_result {
        Ok(backend_resp) => {
            let status = backend_resp.status();
            let resp_headers = backend_resp.headers().clone();
            let body_bytes = match backend_resp.bytes().await {
                Ok(b) => b,
                Err(e) => {
                    error!(request_id = %request_id, error = %e, "Failed to read backend response body");
                    return HttpResponse::BadGateway().json(
                        GatewayError::new("Failed to read upstream response")
                            .with_request_id(&request_id),
                    );
                }
            };

            let mut client_resp = HttpResponse::build(
                actix_web::http::StatusCode::from_u16(status.as_u16())
                    .unwrap_or(actix_web::http::StatusCode::INTERNAL_SERVER_ERROR),
            );

            // Forward safe response headers
            for (name, value) in resp_headers.iter() {
                let lower = name.as_str().to_lowercase();
                if matches!(lower.as_str(), "transfer-encoding" | "connection") {
                    continue;
                }
                if let Ok(hval) = actix_web::http::header::HeaderValue::from_bytes(value.as_bytes()) {
                    client_resp.insert_header((
                        actix_web::http::header::HeaderName::from_bytes(name.as_str().as_bytes()).unwrap(),
                        hval,
                    ));
                }
            }

            client_resp.insert_header(("X-Request-ID", request_id.as_str()));
            client_resp.body(body_bytes)
        }

        Err(e) => {
            error!(request_id = %request_id, error = %e, "Upstream unreachable");
            HttpResponse::BadGateway()
                .json(GatewayError::new("Backend service unavailable").with_request_id(&request_id))
        }
    }
}

// ─────────────────────────────────────────────
// Entry point
// ─────────────────────────────────────────────

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    dotenv().ok();

    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "gateway=info,actix_web=warn".parse().unwrap()),
        )
        .init();

    let config = Config::from_env();

    let quota = Quota::per_second(config.rate_limit_rps).allow_burst(config.rate_limit_burst);
    let rate_limiters: Arc<DashMap<String, (IpLimiter, std::time::Instant)>> =
        Arc::new(DashMap::new());

    // Spawn background worker to asynchronously evict stale limiters
    let rate_limiters_cleanup = rate_limiters.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(60)).await;
            let now = std::time::Instant::now();
            rate_limiters_cleanup.retain(|_, (_, last_seen)| {
                now.duration_since(*last_seen).as_secs() < LIMITER_TTL_SECS
            });
        }
    });

    // Reuse a single HTTP client across all requests (connection-pooled)
    let http_client = Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .expect("Failed to build HTTP client");

    let state = web::Data::new(AppState {
        config: config.clone(),
        http_client,
        rate_limiters,
        quota,
    });

    let allowed_origins = config.allowed_origins.clone();
    let port = config.port;

    info!(
        "Gateway starting on :{port}, proxying → {}",
        config.backend_url
    );

    HttpServer::new(move || {
        // Build CORS middleware from config
        let cors = allowed_origins.iter().fold(
            Cors::default()
                .allowed_methods(vec!["GET", "POST", "PUT", "DELETE", "OPTIONS"])
                .allowed_headers(vec![
                    actix_web::http::header::AUTHORIZATION,
                    actix_web::http::header::CONTENT_TYPE,
                    actix_web::http::header::ACCEPT,
                ])
                .expose_headers(vec!["X-Request-ID"])
                .max_age(3600),
            |cors, origin| cors.allowed_origin(origin),
        );

        App::new()
            .wrap(cors)
            .wrap(Logger::default())
            .app_data(state.clone())
            // Unauthenticated gateway health probe
            .route("/health", web::get().to(health))
            // All other requests → authenticated proxy
            .default_service(web::to(proxy))
    })
    .workers(num_cpus())
    .bind(("0.0.0.0", port))?
    .run()
    .await
}

fn num_cpus() -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4)
}
