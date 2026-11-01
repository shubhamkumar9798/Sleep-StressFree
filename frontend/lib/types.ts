export type TargetDef = {
  name: string;
  task: "classification" | "regression";
  unit: string;
  y: string;
  classes?: string[];
  primary: boolean;
  label_source: string;
  description: string;
};

export type DatasetFile = {
  file: string;
  present: boolean;
  description: string;
  role: string;
  used_by_pipeline: boolean;
  size_bytes: number | null;
};

export type DatasetStatus = {
  dataset: { name: string; version: string; url: string; license: string; authors: string; device_note: string; directory: string };
  files: DatasetFile[];
  available: boolean;
  complete: boolean;
  fingerprint?: string;
  setup_message?: string;
};

export type Metrics = Record<string, number | null>;

export type Run = {
  id: number;
  group_id?: string;
  target: string;
  experiment: string;
  model: string;
  task?: string;
  n_participants: number;
  n_samples: number;
  metrics: Metrics;
  created_at: string;
  dataset_matches_current: boolean;
  config?: { validation?: string; features?: string[]; k_folds?: number; seed?: number; estimator?: string; hyperparameter_tuning?: string };
  details?: {
    folds: { fold: number; n_train: number; n_test: number; n_train_participants: number; n_test_participants: number; participant_overlap: number; balanced_accuracy?: number; mae?: number }[];
    confusion_matrix?: number[][];
    class_labels?: string[];
    classification_report?: Record<string, Record<string, number> | number>;
    class_counts?: Record<string, number>;
    points?: { actual: number; predicted: number }[];
    n_missing_feature_values_imputed?: number;
    missing_by_feature?: Record<string, number>;
  };
};

export type Comparison = {
  target: string;
  model: string;
  experiment: string;
  baseline_experiment: string;
  same_participants_and_folds: boolean;
  test: { n_participants: number; mean_difference: number; metric: string; higher_is_better: boolean; statistic: number | null; p_value: number } | null;
  beats_trivial_baseline: boolean | null;
  interpretation: string;
};

export type TrainedModel = {
  id: number;
  target: string;
  experiment: string;
  model: string;
  feature_names: string[];
  cv_run_id: number;
  is_active: number;
  created_at: string;
  artifact_exists: boolean;
  dataset_matches_current: boolean;
  compatible: boolean;
  incompatibility: string | null;
  artifact_file: string;
};

export type CatalogItem = {
  target: string;
  experiment: string;
  available: boolean;
  reason?: string;
  features: string[];
  name: string;
  description: string;
};

export type Catalog = {
  targets: Record<string, TargetDef>;
  experiments: Record<string, { name: string; description: string }>;
  catalog: CatalogItem[];
  models: Record<"classification" | "regression", Record<string, string>>;
};

export const METRIC_LABELS: Record<string, string> = {
  balanced_accuracy: "Balanced acc.",
  macro_f1: "Macro-F1",
  precision_macro: "Precision (macro)",
  recall_macro: "Recall (macro)",
  roc_auc: "ROC-AUC",
  mae: "MAE",
  rmse: "RMSE",
  r2: "R²",
  pearson_r: "Pearson r",
};
