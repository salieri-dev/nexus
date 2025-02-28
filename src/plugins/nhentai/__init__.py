from src.config.framework import PeerConfigModel

# Register nhentai_blur parameter
PeerConfigModel.register_param(
    param_name="nhentai_blur",
    param_type="plugin:nhentai",
    default=True,
    description="Blur NSFW images with blacklisted tags in nhentai results",
    display_name="NHentai Blur",
    command_name="nhentai_blur"
)