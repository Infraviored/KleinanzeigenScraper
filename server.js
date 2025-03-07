const express = require('express');
const fs = require('fs');
const path = require('path');
const app = express();
const port = 3030;
const { spawn } = require('child_process');

// Serve static files from the public directory
app.use(express.static('public'));
app.use(express.json());

// Path to search URLs file
const searchUrlsPath = path.join(__dirname, 'data', 'search_urls.json');

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

// API endpoint to get search URLs
app.get('/api/search-urls', (req, res) => {
  try {
    if (!fs.existsSync(searchUrlsPath)) {
      fs.writeFileSync(searchUrlsPath, JSON.stringify([
        {
          url: "https://www.kleinanzeigen.de/s-notebooks/preis::1400/rtx4060/k0c278",
          enabled: true,
          name: "RTX 4060 Laptops under 1400€"
        }
      ], null, 2));
    }
    
    const searchUrls = JSON.parse(fs.readFileSync(searchUrlsPath, 'utf8'));
    res.json(searchUrls);
  } catch (error) {
    console.error('Error reading search URLs file:', error);
    res.status(500).json({ error: 'Failed to load search URLs' });
  }
});

// API endpoint to update search URLs
app.post('/api/search-urls', (req, res) => {
  try {
    const searchUrls = req.body;
    fs.writeFileSync(searchUrlsPath, JSON.stringify(searchUrls, null, 2));
    res.json({ success: true });
  } catch (error) {
    console.error('Error updating search URLs file:', error);
    res.status(500).json({ error: 'Failed to update search URLs' });
  }
});

// API endpoint to trigger scraping
app.post('/api/scrape', (req, res) => {
  try {
    const { interval } = req.body;
    
    // Update the cron schedule if provided
    if (interval) {
      const configPath = path.join(__dirname, 'data', 'schedule_config.json');
      fs.writeFileSync(configPath, JSON.stringify({ interval }, null, 2));
    }
    
    // Run the scraper script
    const python = spawn('python3', ['main.py']);
    
    python.stdout.on('data', (data) => {
      console.log(`Python stdout: ${data}`);
    });
    
    python.stderr.on('data', (data) => {
      console.error(`Python stderr: ${data}`);
    });
    
    python.on('close', (code) => {
      console.log(`Python process exited with code ${code}`);
      res.json({ success: true, message: 'Scraping completed' });
    });
    
  } catch (error) {
    console.error('Error triggering scrape:', error);
    res.status(500).json({ error: 'Failed to trigger scraping' });
  }
});

// API endpoint to get current schedule
app.get('/api/schedule', (req, res) => {
  try {
    const configPath = path.join(__dirname, 'data', 'schedule_config.json');
    if (!fs.existsSync(configPath)) {
      fs.writeFileSync(configPath, JSON.stringify({ interval: 60 }, null, 2));
    }
    
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    res.json(config);
  } catch (error) {
    console.error('Error reading schedule config:', error);
    res.status(500).json({ error: 'Failed to load schedule config' });
  }
});

// Serve the main HTML page
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Set up scheduled scraping
function setupScheduledScraping() {
  try {
    const configPath = path.join(__dirname, 'data', 'schedule_config.json');
    if (!fs.existsSync(configPath)) {
      fs.writeFileSync(configPath, JSON.stringify({ interval: 60 }, null, 2));
    }
    
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    const intervalMinutes = config.interval || 60;
    
    console.log(`Setting up scheduled scraping every ${intervalMinutes} minutes`);
    
    // Schedule the first run
    setTimeout(() => {
      runScraper();
      
      // Then set up the interval
      setInterval(runScraper, intervalMinutes * 60 * 1000);
    }, 10000); // Wait 10 seconds before first run
  } catch (error) {
    console.error('Error setting up scheduled scraping:', error);
  }
}

function runScraper() {
  console.log('Running scheduled scraping...');
  const python = spawn('python3', ['main.py']);
  
  python.stdout.on('data', (data) => {
    console.log(`Python stdout: ${data}`);
  });
  
  python.stderr.on('data', (data) => {
    console.error(`Python stderr: ${data}`);
  });
  
  python.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
  });
}

// Start the server and set up scheduled scraping
app.listen(port, () => {
  console.log(`Listings viewer app running at http://localhost:${port}`);
  setupScheduledScraping();
});