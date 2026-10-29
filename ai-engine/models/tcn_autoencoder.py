#!/usr/bin/env python3.12
"""
Temporal Convolutional Network (TCN) Autoencoder for Time-Series Anomaly Detection
Author: Antigravity AI Pair Programmer
Project: Multicloud Monitoring

Architecture:
  Input (Batch, Seq_Len, Features) -> Permute to (Batch, Features, Seq_Len)
     ↓
  Encoder: Dilated Causal Conv1d Residual Blocks (dilation = 1, 2, 4)
     ↓
  Bottleneck Latent Channel Projection (Latent_Dim = 16)
     ↓
  Decoder: Dilated Conv1d Residual Blocks (dilation = 4, 2, 1) + Output Projection
     ↓
  Output Reconstruction X_hat (Batch, Seq_Len, Features)
"""

import torch
import torch.nn as nn

class Chomp1d(nn.Module):
    def __init__(self, chomp_size):
        super().__init__()
        self.chomp_size = chomp_size

    def forward(self, x):
        return x[:, :, :-self.chomp_size].contiguous() if self.chomp_size > 0 else x

class TemporalBlock(nn.Module):
    def __init__(self, n_inputs, n_outputs, kernel_size, stride, dilation, padding, dropout=0.1):
        super().__init__()
        self.conv1 = nn.Conv1d(
            n_inputs, n_outputs, kernel_size,
            stride=stride, padding=padding, dilation=dilation
        )
        self.chomp1 = Chomp1d(padding)
        self.act1 = nn.GELU()
        self.drop1 = nn.Dropout(dropout)

        self.conv2 = nn.Conv1d(
            n_outputs, n_outputs, kernel_size,
            stride=stride, padding=padding, dilation=dilation
        )
        self.chomp2 = Chomp1d(padding)
        self.act2 = nn.GELU()
        self.drop2 = nn.Dropout(dropout)

        self.net = nn.Sequential(
            self.conv1, self.chomp1, self.act1, self.drop1,
            self.conv2, self.chomp2, self.act2, self.drop2
        )
        self.downsample = nn.Conv1d(n_inputs, n_outputs, 1) if n_inputs != n_outputs else None
        self.act_out = nn.GELU()

    def forward(self, x):
        out = self.net(x)
        res = x if self.downsample is None else self.downsample(x)
        return self.act_out(out + res)

class TCNAutoencoder(nn.Module):
    def __init__(self, input_dim=8, hidden_dim=64, latent_dim=16, kernel_size=3, dropout=0.1):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim

        # Encoder dilated stack (dilation 1, 2, 4)
        enc_layers = []
        in_ch = input_dim
        for d in [1, 2, 4]:
            pad = (kernel_size - 1) * d
            enc_layers.append(TemporalBlock(in_ch, hidden_dim, kernel_size, 1, d, pad, dropout))
            in_ch = hidden_dim
        self.encoder_tcn = nn.Sequential(*enc_layers)
        self.to_latent = nn.Conv1d(hidden_dim, latent_dim, kernel_size=1)

        # Decoder stack
        self.from_latent = nn.Conv1d(latent_dim, hidden_dim, kernel_size=1)
        dec_layers = []
        for d in [4, 2, 1]:
            pad = (kernel_size - 1) * d
            dec_layers.append(TemporalBlock(hidden_dim, hidden_dim, kernel_size, 1, d, pad, dropout))
        self.decoder_tcn = nn.Sequential(*dec_layers)
        self.out_proj = nn.Conv1d(hidden_dim, input_dim, kernel_size=1)

    def forward(self, x):
        # x: (batch, seq_len, features) -> (batch, features, seq_len)
        x_t = x.transpose(1, 2)
        z = self.to_latent(self.encoder_tcn(x_t))
        dec = self.decoder_tcn(self.from_latent(z))
        out = self.out_proj(dec).transpose(1, 2)
        return out

    def compute_sample_loss(self, x, x_hat):
        return ((x - x_hat) ** 2).mean(dim=(1, 2))

    def compute_feature_losses(self, x, x_hat):
        return ((x - x_hat) ** 2).mean(dim=1)

