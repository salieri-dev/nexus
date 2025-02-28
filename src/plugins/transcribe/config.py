from src.config.framework import PeerConfigModel

def register_parameters():
    """Register parameters for falai plugin."""
    PeerConfigModel.register_param(
        param_name="transcribe_enabled",
        param_type="plugin:falai",
        default=True,
        description="Convert voice messages to text",
        display_name="Voice Transcription",
        command_name="transcribe"
    )