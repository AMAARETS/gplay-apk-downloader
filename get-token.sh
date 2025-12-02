#!/bin/bash
# Helper script to get auth token for Render deployment

echo "=== GPlay Auth Token for Render ==="
echo ""
echo "Step 1: Getting a valid token..."
python3 gplay-downloader.py auth -r 50

if [ $? -eq 0 ]; then
    echo ""
    echo "Step 2: Token content (copy this to Render):"
    echo "-------------------------------------------"
    cat ~/.gplay-auth.json
    echo ""
    echo "-------------------------------------------"
    echo ""
    echo "Step 3: In Render Dashboard:"
    echo "  1. Go to your service"
    echo "  2. Click 'Environment' in the sidebar"
    echo "  3. Add Environment Variable:"
    echo "     Key: GPLAY_AUTH_TOKEN"
    echo "     Value: [paste the JSON above]"
    echo ""
else
    echo "Failed to get token. Try again."
    exit 1
fi
