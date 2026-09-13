"""VayuDrishti ML inference (identification + intensity classification).

Training lives in identification_model/; this package only loads the exported checkpoints from
backend/models/<task>/ and runs them. Nothing here downloads weights or touches the database.
"""
