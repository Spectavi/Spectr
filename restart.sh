pip install -e .
cd src/spectr/webui/
rm -rf build/
npm install
npm run build
spectr --webui
cd ../../..