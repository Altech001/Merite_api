#!/bin/bash
set -e

# Configuration
# NOTE: This assumes folder "m" is on your Desktop alongside this script.
BACKEND_URL="https://merite.vercel.app/openapi.json"
FRONTEND_PROJECT="../metrie_app" 
API_OUTPUT="$FRONTEND_PROJECT/lib/api"
TEMP_DIR="./temp-client"
OPENAPI_FILE="openapi.json"

echo "Downloading OpenAPI schema from $BACKEND_URL..."
curl -f -s "$BACKEND_URL" > "$OPENAPI_FILE"

# Validate
file_size=$(wc -c < "$OPENAPI_FILE")
if [ "$file_size" -lt 100 ]; then
    echo "Error: OpenAPI file too small ($file_size bytes)"
    cat "$OPENAPI_FILE"
    exit 1
fi
echo "Downloaded OpenAPI schema ($file_size bytes)"

echo "Generating Dart (Dio) client..."
npx @openapitools/openapi-generator-cli generate \
  -i "$OPENAPI_FILE" \
  -g dart-dio \
  -o "$TEMP_DIR" \
  --additional-properties='pubName=api_client,pubLibrary=mintos_api,pubAuthor="Altech <altechalbert01@gmail.com>",pubVersion=1.0.0,pubDescription="Auto-generated API client for Merite",useEnumExtension=true,hideGenerationTimestamp=true,dateLibrary=core' \
  --global-property=apiTests=false,modelTests=false,apiDocs=false,modelDocs=false

echo "Copying to $API_OUTPUT..."
rm -rf "$API_OUTPUT"
mkdir -p "$API_OUTPUT"
cp -r "$TEMP_DIR/lib/"* "$API_OUTPUT/"

# Create README
cat > "$API_OUTPUT/README.md" << 'EOF'
# Merite API Client (Dio)

Auto-generated from OpenAPI spec at https://merite.vercel.app/openapi.json

## Usage
1. Add dependencies to `pubspec.yaml`:
   - dio
   - built_value
   - built_collection

2. Regenerate:
   ```bash
   ./generate-client.sh
