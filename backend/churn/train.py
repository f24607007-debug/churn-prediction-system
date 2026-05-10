import os
from dotenv import load_dotenv
load_dotenv()
import pickle
import logging
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(__file__)
MODELS_DIR = os.path.join(BASE_DIR, 'models')
MODEL_PATH = os.path.join(MODELS_DIR, 'churn_model.pkl')
DATASET_PATH = os.path.join(BASE_DIR, 'ecommerce_churn.csv')

# Features requested
FEATURES = [
    'purchase_frequency',
    'inactivity_days',
    'cart_abandonment_count',
    'refund_count',
    'complaint_count',
    'login_frequency'
]

def download_kaggle_dataset():
    """Attempt to download Kaggle dataset using API keys."""
    try:
        import kaggle
        logger.info("Attempting to download Kaggle dataset...")
        # Note: ankushpanday1/ecommerce-customer-churn-dataset-and-eda is the typical dataset name
        kaggle.api.dataset_download_files('ankushpanday1/ecommerce-customer-churn-dataset-and-eda', path=BASE_DIR, unzip=True)
        logger.info("Kaggle dataset downloaded successfully.")
        
        # Look for the excel or csv file
        files = os.listdir(BASE_DIR)
        for file in files:
            if file.endswith('.csv') or file.endswith('.xlsx'):
                return os.path.join(BASE_DIR, file)
    except Exception as e:
        logger.warning(f"Kaggle download failed or skipped: {e}")
    return None

def generate_synthetic_data(num_samples=1000):
    """Fallback: Generates a realistic synthetic dataset matching our schema."""
    logger.info("Generating synthetic data for training...")
    np.random.seed(42)
    
    data = {
        'purchase_frequency': np.random.randint(0, 20, num_samples),
        'inactivity_days': np.random.randint(0, 60, num_samples),
        'cart_abandonment_count': np.random.randint(0, 15, num_samples),
        'refund_count': np.random.randint(0, 5, num_samples),
        'complaint_count': np.random.randint(0, 5, num_samples),
        'login_frequency': np.random.randint(1, 30, num_samples),
    }
    
    df = pd.DataFrame(data)
    
    # Churn definition: no purchase in 30 days = churned
    # We will simulate this by checking inactivity_days >= 30, adding some noise
    df['Churn'] = (df['inactivity_days'] >= 30).astype(int)
    
    # Add noise
    flip_indices = np.random.choice(df.index, size=int(0.1 * num_samples), replace=False)
    df.loc[flip_indices, 'Churn'] = 1 - df.loc[flip_indices, 'Churn']
    
    df.to_csv(DATASET_PATH, index=False)
    return DATASET_PATH

def load_and_preprocess_data():
    """Loads dataset and maps columns if necessary."""
    dataset_file = download_kaggle_dataset()
    
    if dataset_file and os.path.exists(dataset_file):
        try:
            if dataset_file.endswith('.xlsx'):
                df = pd.read_excel(dataset_file)
            else:
                df = pd.read_csv(dataset_file)
                
            # If using real kaggle data, we would map their columns to ours here.
            # Because the real dataset's exact schema varies, we fall back to synthetic if required columns are missing
            missing_cols = [col for col in FEATURES if col not in df.columns]
            if not missing_cols and 'Churn' in df.columns:
                return df
            else:
                logger.warning(f"Missing expected columns in downloaded data: {missing_cols}. Falling back to synthetic.")
        except Exception as e:
            logger.error(f"Error reading dataset: {e}")
            
    # Fallback to synthetic
    dataset_file = generate_synthetic_data()
    df = pd.read_csv(dataset_file)
    return df

def train_model():
    df = load_and_preprocess_data()
    
    X = df[FEATURES]
    y = df['Churn']
    
    logger.info("Splitting dataset 80/20...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    logger.info("Training Random Forest Classifier...")
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    logger.info("Evaluating Model...")
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    metrics = {
        "Accuracy": accuracy_score(y_test, y_pred),
        "Precision": precision_score(y_test, y_pred, zero_division=0),
        "Recall": recall_score(y_test, y_pred, zero_division=0),
        "F1-score": f1_score(y_test, y_pred, zero_division=0),
        "AUC-ROC": roc_auc_score(y_test, y_prob)
    }
    
    for metric, value in metrics.items():
        logger.info(f"{metric}: {value:.4f}")
        
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(model, f)
        
    logger.info(f"Model saved to {MODEL_PATH}")

if __name__ == '__main__':
    train_model()
