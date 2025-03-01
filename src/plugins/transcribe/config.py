from src.config.framework import PeerConfigModel


def register_parameters():
    """Зарегистрировать параметры для плагина falai."""
    PeerConfigModel.register_param(param_name="transcribe_enabled", param_type="plugin:falai", default=True, description="Преобразовать голосовые сообщения в текст", display_name="Включить расшифровку голосовых сообщений?", command_name="transcribe")
