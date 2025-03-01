from src.config.framework import PeerConfigModel


def register_parameters():
    """Register parameters for DeathByAI plugin."""
    PeerConfigModel.register_param(
        param_name="dbai_submission_window",
        param_type="plugin:deathbyai",
        default=60,  # 60 seconds default
        description="Время в секундах для подачи стратегий в DeathByAI",
        display_name="Какое время в секундах для подачи стратегий в DeathByAI?",
        command_name="dbai_submission_window",
    )
