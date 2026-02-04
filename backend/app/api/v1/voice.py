from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional
import logging
import tempfile
import os
import traceback
import wave
import struct
from pathlib import Path

router = APIRouter()
logger = logging.getLogger(__name__)

WHISPER_MODEL = None

def get_whisper_model():
    """Load faster-whisper model (lazy loading)"""
    global WHISPER_MODEL
    if WHISPER_MODEL is None:
        try:
            logger.info("🔄 Loading faster-whisper model...")
            from faster_whisper import WhisperModel
            WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
            logger.info("✅ faster-whisper model loaded successfully")
        except Exception as e:
            logger.error(f"❌ Failed to load faster-whisper: {e}")
            logger.error(traceback.format_exc())
            raise
    return WHISPER_MODEL


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Convert raw PCM data to WAV format"""
    logger.info(f"🔄 Converting PCM to WAV (rate={sample_rate}, channels={channels})")
    
    # Create WAV file in memory
    import io
    wav_buffer = io.BytesIO()
    
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit samples
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    
    wav_bytes = wav_buffer.getvalue()
    logger.info(f"✅ Converted: {len(pcm_data)} bytes PCM → {len(wav_bytes)} bytes WAV")
    return wav_bytes


@router.post("/transcribe")
async def transcribe_audio(
    audio_file: UploadFile = File(...),
    sample_rate: Optional[int] = Form(16000)
):
    """
    Transcribe audio to text using Whisper.
    Returns just the transcribed text for user confirmation in VR.
    """
    logger.info(f"🎙️ Received audio: {audio_file.filename} ({audio_file.content_type})")
    
    temp_path = None
    
    try:
        # Read audio bytes
        audio_bytes = await audio_file.read()
        logger.info(f"📊 Audio size: {len(audio_bytes):,} bytes")
        
        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")
        
        # Check if it's raw PCM (audio/l16) and convert to WAV
        if audio_file.content_type == "audio/l16" or audio_file.filename.endswith('.pcm'):
            logger.info("🔄 Detected PCM format, converting to WAV...")
            audio_bytes = pcm_to_wav(audio_bytes, sample_rate=sample_rate)
            suffix = ".wav"
        else:
            suffix = Path(audio_file.filename).suffix or ".wav"
        
        # Save to temporary file
        logger.info(f"💾 Creating temp file with suffix: {suffix}")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name
        
        logger.info(f"💾 Saved to temp file: {temp_path}")
        
        # Load Whisper model
        logger.info("🔄 Loading Whisper model...")
        whisper_model = get_whisper_model()
        logger.info("✅ Model loaded, starting transcription...")
        
        # Transcribe with automatic language detection
        transcribe_kwargs = {
            "beam_size": 5
        }

        segments, info = whisper_model.transcribe(
            temp_path,
            **transcribe_kwargs
        )
        
        logger.info("🔄 Processing segments...")
        all_segments = []
        full_text = []
        
        for i, segment in enumerate(segments):
            all_segments.append({
                "id": i,
                "text": segment.text,
                "start": segment.start,
                "end": segment.end
            })
            full_text.append(segment.text)
        
        transcribed_text = " ".join(full_text).strip()
        detected_language = info.language
        
        logger.info(f"✅ Transcription complete ({detected_language}): '{transcribed_text}'")
        
        return {
            "success": True,
            "text": transcribed_text,
            "language": detected_language,
            "confidence": 0.95,  # Whisper doesn't provide this, but we can estimate
            "segments": all_segments,
            "metadata": {
                "audio_size_bytes": len(audio_bytes),
                "sample_rate": sample_rate,
                "duration": all_segments[-1]["end"] if all_segments else 0.0,
                "num_segments": len(all_segments)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Transcription error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Transcription failed: {str(e)}"
        )
    
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
                logger.info(f"🗑️  Cleaned up temp file")
            except Exception as e:
                logger.warning(f"⚠️ Failed to delete temp file: {e}")


# ============================================================================
# NEW: AI PROMPT PROCESSING
# ============================================================================

@router.post("/prompt")
async def process_ai_prompt(
    text: str = Form(...),
    prompt_type: str = Form("general"),  # 'image', 'design', 'question', 'materials', 'general'
    project_id: Optional[int] = Form(None),
    room_id: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None)
):
    """
    Process text prompt for AI operations.
    This is called AFTER user sees transcription and confirms in VR.
    
    Args:
        text: The confirmed text prompt from user
        prompt_type: What to do with the text
        project_id: Optional project context
    """
    logger.info(f"🤖 Processing AI prompt: '{text}' (type: {prompt_type})")
    
    try:
        if prompt_type == "image":
            return await generate_image_from_prompt(text, project_id, room_id, user_id)
        
        elif prompt_type == "design":
            return await process_design_prompt(text, project_id)
        
        elif prompt_type == "question":
            return await answer_question(text, project_id)
        
        elif prompt_type == "materials":
            return await process_material_prompt(text, project_id)
        
        else:  # general
            return await process_general_prompt(text, project_id)
    
    except Exception as e:
        logger.error(f"❌ Prompt processing failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Prompt processing failed: {str(e)}"
        )


async def generate_image_from_prompt(text: str, project_id: Optional[int] = None, room_id: Optional[str] = None, user_id: Optional[str] = None):
    """
    Generate architectural image using Stable Diffusion.
    This is where AI Image Service gets called!
    """
    import uuid
    import time

    generation_id = f"gen_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    logger.info(f"🖼️  Generating image from prompt: '{text}' (ID: {generation_id})")

    try:
        # Import AI Image Service and WebSocket functions
        from app.services.ai_image_service import AIImageService
        from app.api.v1.websocket import send_image_progress_update, complete_image_generation, fail_image_generation

        # Create service instance
        ai_service = AIImageService()

        # Enhance prompt for architectural rendering
        enhanced_prompt = f"architectural rendering: {text}, photorealistic, professional, detailed, 8k, high quality"

        logger.info(f"🎨 Enhanced prompt: '{enhanced_prompt}'")

        # Progress callback function
        async def progress_callback(progress_data):
            await send_image_progress_update(generation_id, progress_data)

        # Generate image with progress tracking
        result = await ai_service.generate_image(
            prompt=enhanced_prompt,
            width=768,
            height=768,
            num_inference_steps=10,  # Fast generation for testing
            guidance_scale=7.5,
            progress_callback=progress_callback if room_id and user_id else None,
            generation_id=generation_id
        )

        if result["success"]:
            logger.info(f"✅ Image generated: {result['image_url']}")

            # Send completion message to WebSocket clients
            if room_id and user_id:
                await complete_image_generation(generation_id, result)

            return {
                "success": True,
                "type": "image_generated",
                "generation_id": generation_id,
                "image_url": result["image_url"],
                "image_data": result.get("image_data"),  # Base64 for immediate display
                "message": f"Generated image from: {text}",
                "metadata": result["metadata"]
            }
        else:
            logger.error(f"❌ Image generation failed: {result.get('error')}")

            # Send failure message to WebSocket clients
            if room_id and user_id:
                await fail_image_generation(generation_id, result.get("error", "Image generation failed"))

            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Image generation failed")
            )

    except Exception as e:
        logger.error(f"❌ Image generation error: {e}")
        logger.error(traceback.format_exc())

        # Send failure message to WebSocket clients
        if room_id and user_id:
            await fail_image_generation(generation_id, str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Image generation failed: {str(e)}"
        )


async def process_design_prompt(text: str, project_id: Optional[int] = None):
    """
    Modify design based on text prompt.
    Example: "make the room 20 feet wide"
    """
    logger.info(f"🏗️  Processing design modification: '{text}'")
    
    # TODO: Implement design modification logic
    # This would parse the text and update design_elements in database
    
    return {
        "success": True,
        "type": "design_modification",
        "message": f"Design modification requested: {text}",
        "action": "parse_and_apply",
        "note": "Design modification not yet implemented"
    }


async def answer_question(text: str, project_id: Optional[int] = None):
    """
    Answer questions about the project using LLM.
    Example: "How much will this cost?"
    """
    logger.info(f"❓ Answering question: '{text}'")
    
    # TODO: Implement Ollama integration for Q&A
    # This would use project data + LLM to answer
    
    return {
        "success": True,
        "type": "answer",
        "question": text,
        "answer": "Question answering not yet implemented. Install Ollama for this feature.",
        "note": "LLM integration pending"
    }


async def process_material_prompt(text: str, project_id: Optional[int] = None):
    """
    Search or suggest materials based on text.
    Example: "I need drywall for the walls"
    """
    logger.info(f"🔨 Processing material request: '{text}'")
    
    # TODO: Search materials database
    # This would query the materials table
    
    return {
        "success": True,
        "type": "materials",
        "query": text,
        "suggestions": [],
        "message": "Material search not yet implemented"
    }


async def process_general_prompt(text: str, project_id: Optional[int] = None):
    """
    General purpose prompt - let AI decide what to do.
    """
    logger.info(f"💬 Processing general prompt: '{text}'")
    
    return {
        "success": True,
        "type": "general",
        "prompt": text,
        "response": f"Received your request: {text}. Specific action handlers not yet implemented."
    }


# ============================================================================
# COMBINED ENDPOINT: Voice → Image (All in one)
# ============================================================================

@router.post("/voice-to-image")
async def voice_to_image(
    audio_file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    sample_rate: Optional[int] = Form(16000),
    auto_generate: bool = Form(False)
):
    """
    Complete voice-to-image pipeline in one call.
    
    If auto_generate=False (default):
        - Returns transcription for user confirmation
        - User must call /prompt endpoint separately
    
    If auto_generate=True:
        - Transcribes and immediately generates image
        - Skips user confirmation step
    """
    logger.info(f"🎙️➡️🖼️  Voice-to-image pipeline (auto={auto_generate})")
    
    # Step 1: Transcribe audio
    transcription_result = await transcribe_audio(
        audio_file=audio_file,
        sample_rate=sample_rate
    )
    
    if not transcription_result["success"]:
        raise HTTPException(status_code=400, detail="Transcription failed")
    
    text = transcription_result["text"]
    logger.info(f"✅ Transcribed: '{text}'")
    
    # If auto_generate, skip confirmation and generate immediately
    if auto_generate:
        logger.info("⚡ Auto-generating image (skipping confirmation)")
        image_result = await generate_image_from_prompt(text, project_id=None)
        
        return {
            "success": True,
            "transcription": transcription_result,
            "image": image_result,
            "workflow": "auto_generated"
        }
    else:
        # Return transcription for user confirmation
        logger.info("⏸️  Returning transcription for user confirmation")
        return {
            "success": True,
            "transcription": transcription_result,
            "workflow": "awaiting_confirmation",
            "next_step": "User should confirm text, then call /prompt endpoint"
        }


@router.get("/status")
async def get_status():
    """Check if voice service is healthy"""
    try:
        logger.info("🔍 Checking Whisper model status...")
        model = get_whisper_model()
        logger.info("✅ Whisper model is available")
        
        # Check if AI Image Service is available
        ai_image_available = False
        try:
            from app.services.ai_image_service import AIImageService
            ai_image_available = True
        except Exception as e:
            logger.warning(f"⚠️  AI Image Service not available: {e}")
        
        return {
            "service": "Voice Processing",
            "status": "healthy",
            "whisper_available": True,
            "whisper_model": "base (faster-whisper)",
            "ai_image_available": ai_image_available,
            "supported_formats": ["audio/l16 (PCM)", "audio/wav", "audio/mp3"],
            "endpoints": {
                "/transcribe": "Audio → Text",
                "/prompt": "Text → AI Action (image/design/question)",
                "/voice-to-image": "Audio → Text → Image (combined)"
            },
            "temp_dir": tempfile.gettempdir()
        }
    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")
        return {
            "service": "Voice Processing",
            "status": "error",
            "whisper_available": False,
            "error": str(e)
        }