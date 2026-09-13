"""Track / intensity / pressure prediction — pipeline stage 3.

One code path for training (prediction_model/) and serving (this backend): observation validation,
feature engineering, temporal sequences, baselines, the temporal model and post-processing all live
here, so a forecast served by the API is built exactly like the forecasts the model was evaluated on.
"""
