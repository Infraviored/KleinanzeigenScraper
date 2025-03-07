/**
 * Example script demonstrating how to run the Python scraper from Node.js
 * This shows the interaction between the server and the scraper
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// Get the absolute path to the virtual environment's Python executable
const venvPath = path.join(__dirname, 'kleinanzeigenScraper', 'bin', 'python');

// Function to run the scraper with arguments
function runScraper(mode = 'both', urls = null, maxListings = null) {
  console.log(`Starting scraper in ${mode} mode...`);
  
  // Build arguments array
  const args = ['main.py', '--mode', mode];
  
  // Add URLs if provided
  if (urls && Array.isArray(urls) && urls.length > 0) {
    args.push('--urls');
    urls.forEach(url => args.push(url));
  }
  
  // Add max listings if provided
  if (maxListings) {
    args.push('--max-listings');
    args.push(maxListings.toString());
  }
  
  console.log(`Running command: ${venvPath} ${args.join(' ')}`);
  
  // Spawn the Python process
  const pythonProcess = spawn(venvPath, args);
  
  // Handle stdout
  pythonProcess.stdout.on('data', (data) => {
    console.log(`Scraper output: ${data}`);
  });
  
  // Handle stderr
  pythonProcess.stderr.on('data', (data) => {
    console.error(`Scraper error: ${data}`);
  });
  
  // Handle process exit
  pythonProcess.on('close', (code) => {
    console.log(`Scraper process exited with code ${code}`);
    
    // Check if listings file exists and has data
    const listingsPath = path.join(__dirname, 'data', 'listings.json');
    if (fs.existsSync(listingsPath)) {
      try {
        const listings = JSON.parse(fs.readFileSync(listingsPath, 'utf8'));
        console.log(`Found ${listings.length} listings in the data file.`);
      } catch (error) {
        console.error('Error reading listings file:', error);
      }
    } else {
      console.log('No listings file found.');
    }
  });
  
  return pythonProcess;
}

// Example usage:
// 1. Run scraper in both mode (scrape and process)
runScraper('both');

// 2. Run scraper with specific URL (uncomment to use)
/*
runScraper('scrape', [
  'https://www.kleinanzeigen.de/s-notebooks/preis::1400/rtx4060/k0c278'
], 10);
*/

// 3. Run only the processing part
/*
runScraper('process');
*/ 