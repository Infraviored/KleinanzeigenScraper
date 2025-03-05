const express = require('express');
const fs = require('fs');
const path = require('path');
const app = express();
const port = 3030;

// Serve static files from the public directory
app.use(express.static('public'));

// API endpoint to get the listings data
app.get('/api/listings', (req, res) => {
  try {
    const dataPath = path.join(__dirname, 'data', 'listings.json');
    const listings = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
    res.json(listings);
  } catch (error) {
    console.error('Error reading listings file:', error);
    res.status(500).json({ error: 'Failed to load listings data' });
  }
});

// Serve the main HTML page
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(port, () => {
  console.log(`Listings viewer app running at http://localhost:${port}`);
});