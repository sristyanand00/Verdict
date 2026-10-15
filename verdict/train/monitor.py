"""Training monitoring and metrics tracking.

    TrainingMonitor
    - Track loss curves, rewards, accuracy
    - Save metrics to JSON
    - Generate plots
"""

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class Metric:
    """Single metric value with timestamp."""
    
    step: int
    epoch: int
    value: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class EpochMetrics:
    """Metrics for one training epoch."""
    
    epoch: int
    step: int
    loss: float
    reward_mean: float
    reward_std: float
    accuracy: float
    duration_s: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class TrainingMonitor:
    """Track training metrics and save to file."""
    
    def __init__(self, output_dir: Path | str = "results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        
        # Metrics storage
        self.losses = []
        self.rewards = []
        self.accuracies = []
        self.epoch_metrics = []
        
        # Metadata
        self.start_time = datetime.now()
        self.num_steps = 0
    
    def log_step(
        self,
        step: int,
        epoch: int,
        loss: float,
        reward: Optional[float] = None,
        accuracy: Optional[float] = None,
    ) -> None:
        """Log metrics for a single training step.
        
        Args:
            step: Global step number
            epoch: Current epoch
            loss: Loss value
            reward: Reward value (optional)
            accuracy: Accuracy (optional)
        """
        self.losses.append(Metric(step=step, epoch=epoch, value=loss))
        
        if reward is not None:
            self.rewards.append(Metric(step=step, epoch=epoch, value=reward))
        
        if accuracy is not None:
            self.accuracies.append(Metric(step=step, epoch=epoch, value=accuracy))
        
        self.num_steps = step
    
    def log_epoch(
        self,
        epoch: int,
        step: int,
        loss: float,
        reward_mean: float,
        reward_std: float = 0.0,
        accuracy: float = 0.0,
        duration_s: float = 0.0,
    ) -> None:
        """Log metrics for epoch completion.
        
        Args:
            epoch: Epoch number
            step: Global step at epoch end
            loss: Average loss for epoch
            reward_mean: Mean reward
            reward_std: Std dev of rewards
            accuracy: Accuracy
            duration_s: Time taken for epoch
        """
        metrics = EpochMetrics(
            epoch=epoch,
            step=step,
            loss=loss,
            reward_mean=reward_mean,
            reward_std=reward_std,
            accuracy=accuracy,
            duration_s=duration_s,
        )
        self.epoch_metrics.append(metrics)
        
        self.logger.info(
            f"Epoch {epoch} | "
            f"Loss: {loss:.4f} | "
            f"Reward: {reward_mean:.4f}±{reward_std:.4f} | "
            f"Acc: {accuracy:.2%} | "
            f"Time: {duration_s:.1f}s"
        )
    
    def get_summary(self) -> dict:
        """Get summary statistics."""
        def safe_stats(metrics):
            if not metrics:
                return {"mean": 0, "min": 0, "max": 0, "std": 0}
            values = [m.value for m in metrics]
            return {
                "mean": float(np.mean(values)),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "std": float(np.std(values)),
            }
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "num_epochs": len(self.epoch_metrics),
            "num_steps": self.num_steps,
            "elapsed_s": elapsed,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "loss": safe_stats(self.losses),
            "reward": safe_stats(self.rewards),
            "accuracy": safe_stats(self.accuracies),
        }
    
    def save(self, filename: str = "training_metrics.json") -> Path:
        """Save all metrics to JSON file.
        
        Args:
            filename: Output filename
        
        Returns:
            Path to saved file
        """
        output_path = self.output_dir / filename
        
        # Convert to serializable format
        data = {
            "summary": self.get_summary(),
            "epochs": [asdict(m) for m in self.epoch_metrics],
            "steps": {
                "losses": [asdict(m) for m in self.losses],
                "rewards": [asdict(m) for m in self.rewards],
                "accuracies": [asdict(m) for m in self.accuracies],
            },
        }
        
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        
        self.logger.info(f"✓ Saved metrics to {output_path}")
        return output_path
    
    def plot_loss_curve(self, output_file: Optional[str] = None) -> None:
        """Generate loss curve plot.
        
        Args:
            output_file: Output PNG filename (optional)
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            self.logger.warning("matplotlib not installed, skipping plot")
            return
        
        if not self.losses:
            self.logger.warning("No loss data to plot")
            return
        
        steps = [m.step for m in self.losses]
        values = [m.value for m in self.losses]
        
        plt.figure(figsize=(10, 6))
        plt.plot(steps, values, linewidth=2)
        plt.xlabel("Training Step")
        plt.ylabel("Loss")
        plt.title("Training Loss Curve")
        plt.grid(True, alpha=0.3)
        
        if output_file:
            output_path = self.output_dir / output_file
            plt.savefig(output_path, dpi=100, bbox_inches="tight")
            self.logger.info(f"✓ Saved plot to {output_path}")
        else:
            plt.show()
        
        plt.close()
    
    def plot_metrics(self, output_file: Optional[str] = None) -> None:
        """Generate multi-metric plot.
        
        Args:
            output_file: Output PNG filename (optional)
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            self.logger.warning("matplotlib not installed, skipping plot")
            return
        
        if not self.epoch_metrics:
            self.logger.warning("No epoch data to plot")
            return
        
        epochs = [m.epoch for m in self.epoch_metrics]
        losses = [m.loss for m in self.epoch_metrics]
        rewards = [m.reward_mean for m in self.epoch_metrics]
        accuracies = [m.accuracy for m in self.epoch_metrics]
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        
        # Loss
        axes[0].plot(epochs, losses, marker="o", linewidth=2)
        axes[0].set_xlabel("Epoch")
        axes[0].set_ylabel("Loss")
        axes[0].set_title("Loss over Epochs")
        axes[0].grid(True, alpha=0.3)
        
        # Reward
        axes[1].plot(epochs, rewards, marker="o", linewidth=2, color="green")
        axes[1].set_xlabel("Epoch")
        axes[1].set_ylabel("Mean Reward")
        axes[1].set_title("Reward over Epochs")
        axes[1].grid(True, alpha=0.3)
        
        # Accuracy
        axes[2].plot(epochs, accuracies, marker="o", linewidth=2, color="orange")
        axes[2].set_xlabel("Epoch")
        axes[2].set_ylabel("Accuracy")
        axes[2].set_title("Accuracy over Epochs")
        axes[2].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if output_file:
            output_path = self.output_dir / output_file
            plt.savefig(output_path, dpi=100, bbox_inches="tight")
            self.logger.info(f"✓ Saved plot to {output_path}")
        else:
            plt.show()
        
        plt.close()
