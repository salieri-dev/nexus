import os
from typing import AsyncGenerator, Dict, Any

import fal_client
from structlog import get_logger

log = get_logger(__name__)


async def upload_file(file_path: str) -> str:
    """
    Upload a file to fal-ai.
    
    Args:
        file_path: Path to the file to upload
        
    Returns:
        URL of the uploaded file
        
    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    log.info(f"Uploading file: {file_path}")
    return await fal_client.upload_file_async(file_path)


async def transcribe_audio(file_path: str, language: str = "ru") -> Dict[str, Any]:
    """
    Transcribe an audio file using fal-ai/wizper model.
    
    Args:
        file_path: Path to the audio file
        language: Language of the audio (default: "ru")
        
    Returns:
        Dictionary containing transcription result
    """
    try:
        url = await upload_file(file_path)

        log.info("Submitting transcription job")
        handler = await fal_client.submit_async(
            "fal-ai/wizper",
            arguments={"audio_url": url, "task": "transcribe", "language": language}
        )

        log.info("Waiting for transcription result")
        result = await handler.get()

        transcription = result.get("text", "")
        if not transcription:
            log.info("Transcription is empty")

        return {"success": True, "transcription": transcription, "full_result": result}

    except FileNotFoundError as e:
        log.info(f"File error: {str(e)}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        log.info(f"Unexpected error: {str(e)}")
        return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}


async def generate_image(model_name: str, payload: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generate an image using specified fal-ai model.
    
    Args:
        model_name: Name of the fal-ai model to use
        payload: Complete payload for image generation
    
    Yields:
        Dictionary containing event information during generation
    """
    handler = await fal_client.submit_async(
        model_name,
        arguments=payload
    )

    async for event in handler.iter_events(with_logs=True):
        yield event

    result = await handler.get()
    yield result


async def generate_image_sync(model_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate an image synchronously using specified fal-ai model.
    
    Args:
        model_name: Name of the fal-ai model to use
        payload: Complete payload for image generation
    
    Returns:
        Dictionary containing the final generation result
    """
    handler = await fal_client.submit_async(
        model_name,
        arguments=payload
    )

    return await handler.get()


async def upscale_image(image_path: str, upscale_factor: int = 2) -> Dict[str, Any]:
    """
    Upscale an image using fal-ai/clarity-upscaler model.
    
    Args:
        image_path: Path to the image file
        upscale_factor: Factor by which to upscale the image (default: 2)
        
    Returns:
        Dictionary containing:
            - success: bool indicating if upscaling was successful
            - image: dict with url, width, height if successful
            - error: error message if not successful
            - model_params: parameters used for upscaling
    """
    try:
        # Upload the image file
        url = await upload_file(image_path)

        model_params = {
            "image_url": url,
            "prompt": "masterpiece, best quality, highres",
            "upscale_factor": upscale_factor,
            "negative_prompt": "(worst quality, low quality, normal quality:2), lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
            "enable_safety_checker": False,
        }

        log.info("Submitting upscale job")
        result = await fal_client.submit_async(
            "fal-ai/clarity-upscaler",
            arguments=model_params
        )

        final_result = await result.get()

        if not final_result or not isinstance(final_result, dict) or "image" not in final_result:
            log.error("Invalid response structure from fal.ai API")
            return {
                "success": False,
                "error": "Invalid response from upscaling service"
            }

        return {
            "success": True,
            "image": final_result["image"],
            "model_params": {
                **model_params,
                "model": "fal-ai/clarity-upscaler",
                "seed": final_result.get("seed"),
                "timings": final_result.get("timings")
            }
        }

    except FileNotFoundError as e:
        log.error(f"File error: {str(e)}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        log.error(f"Upscale error: {str(e)}")
        return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}
