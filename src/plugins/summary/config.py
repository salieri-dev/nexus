from src.config.framework import PeerConfigModel


def register_parameters():
    """Регистрация параметров для плагина суммаризации."""
    PeerConfigModel.register_param(param_name="summary_enabled", param_type="plugin:summary", default=False, description="Генерировать ежедневные сводки чатов", display_name="Включить суммаризацию чата?", command_name="summary")
