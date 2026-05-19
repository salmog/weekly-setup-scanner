import os

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

MODEL_PATH = "/code/rf_model.pkl"


def train_model():
    print(" Training Random Forest Classifier (Chronological Split)...")
    try:
        df = pd.read_csv("/code/trade_features.csv")
    except FileNotFoundError:
        print(" Error: trade_features.csv not found. Run dataset_builder.py first.")
        return

    df["Entry_Time"] = pd.to_datetime(df["Entry_Time"])
    df = df.sort_values("Entry_Time")

    features = [
        "trend_slope_150",
        "distance_from_sma",
        "atr_percent",
        "volume_ratio",
        "breakout_strength",
        "range_expansion",
        "higher_tf_alignment",
        "market_regime",
    ]

    # 70/30 Chronological Split
    split_idx = int(len(df) * 0.7)
    train = df.iloc[:split_idx]
    test = df.iloc[split_idx:]

    X_train, y_train = train[features], train["Outcome"]
    X_test, y_test = test[features], test["Outcome"]

    # Train Model
    model = RandomForestClassifier(
        n_estimators=100, max_depth=5, random_state=42, class_weight="balanced"
    )
    model.fit(X_train, y_train)

    # Validate
    preds = model.predict(X_test)
    print("\n Classification Report (Unseen Data):")
    print(classification_report(y_test, preds))

    joblib.dump(model, MODEL_PATH)
    print(f" Model saved to {MODEL_PATH}")


class MLFilter:
    def __init__(self):
        if os.path.exists(MODEL_PATH):
            self.model = joblib.load(MODEL_PATH)
        else:
            self.model = None

    def score_trade(self, features_dict) -> float:
        if not self.model:
            return 1.0
        df = pd.DataFrame([features_dict])
        return self.model.predict_proba(df)[0][1]


if __name__ == "__main__":
    train_model()
