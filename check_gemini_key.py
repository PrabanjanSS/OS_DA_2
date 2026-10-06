"""
Script to verify Gemini API key configuration
"""
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')

print("=" * 60)
print("Gemini API Key Verification")
print("=" * 60)
print(f"API Key: {api_key[:20]}...{api_key[-10:] if len(api_key) > 30 else api_key}")
print(f"API Key Length: {len(api_key)} characters")
print()

print("Attempting to configure and test...")
try:
    genai.configure(api_key=api_key)
    
    # Try to list models to verify the key works
    print("Listing available models...")
    models = list(genai.list_models())
    print(f"✓ Found {len(models)} models")
    
    # Show first few models
    print("\nFirst 5 available models:")
    for i, m in enumerate(models[:5]):
        print(f"  {i+1}. {m.name}")
    
    print("\n✓ API key is valid and working!")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    print("\nPossible issues:")
    print("1. API key is invalid or expired")
    print("2. Gemini API is not enabled in your Google Cloud project")
    print("3. API key has restrictions (IP, referrer, etc.)")
    print("4. You need to enable the Generative Language API in Google Cloud Console")
    
print("\n" + "=" * 60)
print("Next Steps:")
print("=" * 60)
print("1. Go to: https://console.cloud.google.com/")
print("2. Select your project")
print("3. Go to APIs & Services > Library")
print("4. Search for 'Generative Language API' and enable it")
print("5. Go to APIs & Services > Credentials")
print("6. Edit your API key and ensure no restrictions block your access")
print("7. Wait a few minutes for changes to propagate")
print("=" * 60)
