#!/usr/bin/env python3
"""
Test script for AI Image Service with Compel integration.
Verifies that long prompts work correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services import AIImageService


async def test_short_prompt():
    """Test with prompt under 77 tokens."""
    print("\n" + "="*70)
    print("TEST 1: Short Prompt (Under 77 tokens)")
    print("="*70)
    
    service = AIImageService()
    
    prompt = "dog house, cedar siding, gable roof, photorealistic, 8k"
    
    token_count = service.count_tokens(prompt)
    print(f"Prompt: {prompt}")
    print(f"Token count: {token_count}/77")
    
    if token_count <= 77:
        print("✅ Prompt fits in 77 tokens - will use standard generation")
    else:
        print("❌ Prompt exceeds 77 tokens - will use Compel")
    
    result = await service.generate_image(
        prompt=prompt,
        num_images=1,
        num_inference_steps=20  # Fast for testing
    )
    
    if result["success"]:
        print(f"✅ Generated successfully")
        print(f"   Image URL: {result['images'][0]['image_url']}")
        print(f"   Used Compel: {result['metadata']['used_compel']}")
    else:
        print(f"❌ Generation failed: {result['error']}")


async def test_long_prompt():
    """Test with prompt over 77 tokens (requires Compel)."""
    print("\n" + "="*70)
    print("TEST 2: Long Prompt (Over 77 tokens - Requires Compel)")
    print("="*70)
    
    service = AIImageService()
    
    # This prompt is intentionally very long
    prompt = """professional architectural rendering of a modern dog house kennel,
    exterior front three-quarter view angle,
    STRUCTURE: rectangular base 4 feet wide by 8 feet long by 5 feet tall,
    gable roof with 30 degree pitch angle,
    single entrance opening centered on front facade,
    MATERIALS: tongue and groove cedar wood siding vertical planks,
    natural finish with visible wood grain texture,
    dark brown asphalt composite shingle roofing,
    wooden trim and corner boards,
    STYLE: modern craftsman residential architecture,
    southern california backyard design aesthetic,
    clean professional construction quality,
    QUALITY: photorealistic architectural visualization,
    professional construction photography,
    natural outdoor daylight lighting,
    sharp focus with high detail,
    8k resolution quality"""
    
    token_count = service.count_tokens(prompt)
    print(f"Prompt (first 100 chars): {prompt[:100]}...")
    print(f"Token count: {token_count}/77")
    
    if token_count > 77:
        print("✅ Prompt exceeds 77 tokens - Compel will be used")
    else:
        print("⚠️  Prompt fits in 77 tokens - Compel not needed")
    
    result = await service.generate_image(
        prompt=prompt,
        num_images=1,
        num_inference_steps=20  # Fast for testing
    )
    
    if result["success"]:
        print(f"✅ Generated successfully with long prompt!")
        print(f"   Image URL: {result['images'][0]['image_url']}")
        print(f"   Used Compel: {result['metadata']['used_compel']}")
        print(f"   Prompt tokens: {result['metadata']['prompt_tokens']}")
    else:
        print(f"❌ Generation failed: {result['error']}")


async def test_voice_to_image():
    """Test voice input to image generation."""
    print("\n" + "="*70)
    print("TEST 3: Voice-to-Image Generation")
    print("="*70)
    
    service = AIImageService()
    
    # Simulate voice input
    voice_text = """Doghouse made out of tongue and groove cedar siding 
    that is 4 feet wide by 8 feet long by 5 feet high 
    with a 30 degree pitched roof, single dark brown"""
    
    print(f"Voice input: {voice_text}")
    
    result = await service.generate_from_voice_input(
        voice_text=voice_text,
        num_options=2  # Generate 2 options
    )
    
    if result["success"]:
        print(f"✅ Generated {result['count']} options from voice input")
        for i, img in enumerate(result['images']):
            print(f"   Option {i+1}: {img['image_url']}")
        print(f"   Used Compel: {result['metadata']['used_compel']}")
        print(f"   Prompt tokens: {result['metadata']['prompt_tokens']}")
    else:
        print(f"❌ Generation failed: {result['error']}")


async def test_prompt_compression():
    """Test prompt compression fallback."""
    print("\n" + "="*70)
    print("TEST 4: Prompt Compression")
    print("="*70)
    
    service = AIImageService()
    
    long_prompt = """professional architectural rendering,
    dog house kennel structure, exterior front view,
    DIMENSIONS: 4 feet wide by 8 feet long by 5 feet tall walls,
    gable roof with 30 degree pitch angle,
    MATERIALS: tongue and groove cedar wood siding vertical orientation"""
    
    original_tokens = service.count_tokens(long_prompt)
    print(f"Original prompt tokens: {original_tokens}")
    print(f"Original: {long_prompt[:80]}...")
    
    compressed = service.compress_prompt(long_prompt)
    compressed_tokens = service.count_tokens(compressed)
    
    print(f"\nCompressed prompt tokens: {compressed_tokens}")
    print(f"Compressed: {compressed}")
    
    if compressed_tokens <= 75:
        print(f"✅ Successfully compressed from {original_tokens} to {compressed_tokens} tokens")
    else:
        print(f"⚠️  Still {compressed_tokens} tokens after compression")


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("AI IMAGE SERVICE - COMPEL INTEGRATION TESTS")
    print("="*70)
    
    try:
        # Test 1: Short prompt
        await test_short_prompt()
        
        # Test 2: Long prompt (main test for Compel)
        await test_long_prompt()
        
        # Test 3: Voice-to-image
        await test_voice_to_image()
        
        # Test 4: Compression fallback
        await test_prompt_compression()
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
