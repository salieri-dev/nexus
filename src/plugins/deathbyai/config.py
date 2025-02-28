from src.config.framework import PeerConfigModel


def register_parameters():
    """Register parameters for DeathByAI plugin."""
    PeerConfigModel.register_param(
        param_name="dbai_submission_window",
        param_type="plugin:deathbyai",
        default=60,  # 60 seconds default
        description="Time in seconds for submitting strategies in DeathByAI",
        display_name="Submission Window",
        command_name="dbai_submission_window",
    )
