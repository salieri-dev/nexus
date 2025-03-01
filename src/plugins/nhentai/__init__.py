from src.config.framework import PeerConfigModel

# Register nhentai_blur parameter
PeerConfigModel.register_param(param_name="nhentai_blur", param_type="plugin:nhentai", default=True, description="Размывать изображения с табу в результатах NHentai?", display_name="Размывать изображения с табу в результатах NHentai?", command_name="nhentai_blur")
