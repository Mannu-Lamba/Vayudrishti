"""Load the observation table and split it into storm-level train / val / test sample sets."""

from __future__ import annotations

import pandas as pd

from src.common import project_path, sequence_config
from ml.prediction.features import validate_observations
from ml.prediction.sequences import SequenceSet, build_samples

OBSERVATIONS_FILE = "observations.csv.gz"
SPLITS_FILE = "storm_splits.csv"


def load_observations(cfg: dict) -> pd.DataFrame:
    raw = pd.read_csv(project_path(cfg, "processed", OBSERVATIONS_FILE), keep_default_na=False, na_values=[""], low_memory=False)
    clean, _ = validate_observations(raw)
    return clean


def load_splits(cfg: dict) -> pd.DataFrame:
    return pd.read_csv(project_path(cfg, "splits", SPLITS_FILE), keep_default_na=False, na_values=[""])


def split_samples(cfg: dict, split: str, obs: pd.DataFrame | None = None, splits: pd.DataFrame | None = None) -> SequenceSet:
    obs = load_observations(cfg) if obs is None else obs
    splits = load_splits(cfg) if splits is None else splits
    storms = set(splits.loc[splits.split == split, "storm_id"])
    return build_samples(obs[obs.storm_id.isin(storms)], sequence_config(cfg))
