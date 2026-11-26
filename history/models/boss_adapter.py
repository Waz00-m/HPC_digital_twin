"""Replace this adapter when the model and its input/output contract are supplied."""
MODEL_NAME = "boss-model-pending"
MODEL_VERSION = "not-supplied"
REQUIRED_COLUMNS = ("thing_id", "observed_at", "weight_kg", "capacity_kg")


def run(rows, context):
    # rows: immutable-database snapshot features, ordered by observation time.
    # context: input schema, exact snapshot IDs/hash, query window and capture notices.
    # Convert to the model's expected array/DataFrame/tensor here, call it, and
    # return JSON-serializable output. No model library is assumed or installed.
    raise NotImplementedError("The model and its input/output contract have not been supplied yet.")
