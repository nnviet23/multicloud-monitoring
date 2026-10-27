#!/usr/bin/env python3.12
"""
GRU Autoencoder Architecture for Multivariate Time-Series Anomaly Detection
Author: Antigravity AI Pair Programmer
Project: Multicloud Monitoring

Architecture:
  Input (Batch, Seq_Len, Features)
     ↓
  Encoder: 2-Layer GRU (hidden=64, dropout=0.1)
     ↓
  Bottleneck Latent Vector Z (Batch, Latent_Dim=16)
     ↓
  Repeat Vector across Seq_Len
     ↓
  Decoder: 2-Layer GRU (hidden=64, dropout=0.1)
     ↓
  Projection Linear Layer (hidden=64 -> Features=14)
     ↓
  Output Reconstruction X_hat (Batch, Seq_Len, Features)
"""

import torch
import torch.nn as nn

class GRUEncoder(nn.Module):
    def __init__(self, input_dim=14, hidden_dim=64, latent_dim=16, num_layers=2, dropout=0.1):
        super().__init__()
        self.num_layers = num_layers
        self.hidden_dim = hidden_dim
        self.gru = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0
        )
        self.fc_latent = nn.Linear(hidden_dim, latent_dim)

    def forward(self, x):
        # x: (batch_size, seq_len, input_dim)
        _, h_n = self.gru(x)
        # Take the top layer hidden state from the last timestep: h_n[-1]
        last_hidden = h_n[-1]  # (batch_size, hidden_dim)
        z = self.fc_latent(last_hidden)  # (batch_size, latent_dim)
        return z

class GRUDecoder(nn.Module):
    def __init__(self, latent_dim=16, hidden_dim=64, output_dim=14, num_layers=2, dropout=0.1):
        super().__init__()
        self.num_layers = num_layers
        self.hidden_dim = hidden_dim
        self.fc_up = nn.Linear(latent_dim, hidden_dim)
        self.gru = nn.GRU(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0
        )
        self.fc_out = nn.Linear(hidden_dim, output_dim)

    def forward(self, z, seq_len):
        # z: (batch_size, latent_dim)
        z_expanded = self.fc_up(z)  # (batch_size, hidden_dim)
        # Repeat across sequence length: (batch_size, seq_len, hidden_dim)
        decoder_input = z_expanded.unsqueeze(1).repeat(1, seq_len, 1)
        out, _ = self.gru(decoder_input)
        reconstruction = self.fc_out(out)  # (batch_size, seq_len, output_dim)
        return reconstruction

class GRUAutoencoder(nn.Module):
    def __init__(self, input_dim=14, hidden_dim=64, latent_dim=16, num_layers=2, dropout=0.1):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.num_layers = num_layers

        self.encoder = GRUEncoder(input_dim, hidden_dim, latent_dim, num_layers, dropout)
        self.decoder = GRUDecoder(latent_dim, hidden_dim, input_dim, num_layers, dropout)

    def forward(self, x):
        seq_len = x.size(1)
        z = self.encoder(x)
        x_hat = self.decoder(z, seq_len)
        return x_hat

    def encode(self, x):
        return self.encoder(x)

    def compute_sample_loss(self, x, x_hat):
        """
        Computes Mean Squared Error (MSE) per sequence window: (batch_size,)
        """
        squared_diff = (x - x_hat) ** 2
        return squared_diff.mean(dim=(1, 2))

    def compute_feature_losses(self, x, x_hat):
        """
        Computes Mean Squared Error per individual feature: (batch_size, num_features)
        Used for Root Cause Analysis (RCA) to find which service contributed most to the anomaly.
        """
        squared_diff = (x - x_hat) ** 2
        return squared_diff.mean(dim=1)

