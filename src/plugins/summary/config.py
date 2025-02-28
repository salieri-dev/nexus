from src.config.framework import PeerConfigModel


def register_parameters():
    """Register parameters for summary plugin."""
    PeerConfigModel.register_param(param_name="summary_enabled", param_type="plugin:summary", default=False, description="Generate daily chat summaries", display_name="Chat Summarization", command_name="summary")
