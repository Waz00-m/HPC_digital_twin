"""Replace this adapter when the model and its input/output contract are supplied."""
MODEL_NAME = "boss-model-pending"
MODEL_VERSION = "not-supplied"
REQUIRED_COLUMNS = ("thing_id", "observed_at", "weight_kg", "capacity_kg")


def run(rows, context):
    # rows: stored features; --input-series samples includes repeated timed rows
    # with sample_id/sampled_at. reading_at remains the original receipt time.
    # context: selected series, exact sample/snapshot IDs/hash and capture notices.
    # Convert to the model's expected array/DataFrame/tensor here, call it, and
    # return JSON-serializable output. No model library is assumed or installed.
    raise NotImplementedError("The model and its input/output contract have not been supplied yet.")
