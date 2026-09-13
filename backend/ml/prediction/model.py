"""Multi-task temporal forecaster.

    sequential features [B, steps, F]
          → encoder (GRU | LSTM | Transformer — config `architecture`)
          → last-step hidden representation
          → shared FC (ReLU, dropout)
          ├── track head      → Δlat, Δlon per horizon
          ├── intensity head  → Δwind per horizon
          └── pressure head   → Δpressure per horizon

Outputs are standardised changes from T0, [B, H, 4]; the Normalizer converts them to degrees / kt /
hPa. Swapping the encoder (e.g. to the Transformer) changes nothing else in the pipeline.
"""

from __future__ import annotations

import torch
from torch import nn

MODEL_SPEC_KEYS = ("n_features", "n_steps", "n_horizons", "architecture", "hidden", "layers", "dropout", "head_hidden", "n_heads")


class TrackForecaster(nn.Module):
    def __init__(self, n_features: int, n_steps: int, n_horizons: int, architecture: str = "gru", hidden: int = 128,
                 layers: int = 2, dropout: float = 0.2, head_hidden: int = 128, n_heads: int = 4):
        super().__init__()
        self.architecture = architecture
        self.n_horizons = n_horizons
        if architecture in ("gru", "lstm"):
            rnn = nn.GRU if architecture == "gru" else nn.LSTM
            self.encoder = rnn(n_features, hidden, num_layers=layers, batch_first=True, dropout=dropout if layers > 1 else 0.0)
        elif architecture == "transformer":
            self.input_proj = nn.Linear(n_features, hidden)
            self.position = nn.Parameter(torch.zeros(1, n_steps, hidden))
            layer = nn.TransformerEncoderLayer(hidden, n_heads, dim_feedforward=2 * hidden, dropout=dropout, batch_first=True)
            self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        else:
            raise ValueError(f"unknown architecture {architecture!r} (gru | lstm | transformer)")
        self.shared = nn.Sequential(nn.Linear(hidden, head_hidden), nn.ReLU(), nn.Dropout(dropout))
        self.track_head = nn.Linear(head_hidden, n_horizons * 2)
        self.intensity_head = nn.Linear(head_hidden, n_horizons)
        self.pressure_head = nn.Linear(head_hidden, n_horizons)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        if self.architecture == "transformer":
            return self.encoder(self.input_proj(x) + self.position[:, : x.shape[1]])[:, -1]
        out, _ = self.encoder(x)
        return out[:, -1]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.shared(self.encode(x))
        track = self.track_head(z).view(-1, self.n_horizons, 2)
        return torch.cat([track, self.intensity_head(z).unsqueeze(-1), self.pressure_head(z).unsqueeze(-1)], dim=-1)


def build_model(spec: dict) -> TrackForecaster:
    return TrackForecaster(**{key: spec[key] for key in MODEL_SPEC_KEYS if key in spec})
