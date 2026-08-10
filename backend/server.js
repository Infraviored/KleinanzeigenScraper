const express = require('express');
const fs = require('fs');
const path = require('path');

// Load environment variables from .env file if it exists
try {
  const envPath = path.join(__dirname, '..', '.env');
  if (fs.existsSync(envPath)) {
    process.loadEnvFile(envPath);
  }
} catch (error) {
  console.warn('Failed to load .env file:', error.message);
}

const app = express();
const port = 3030;
const { spawn } = require('child_process');
const sqlite3 = require('sqlite3').verbose();
const jwt = require('jsonwebtoken');
const bcrypt = require('bcrypt');
if (process.env.NODE_ENV === 'production' && !process.env.JWT_SECRET) {
  console.error("FATAL: JWT_SECRET environment variable is required in production!");
  process.exit(1);
}
const JWT_SECRET = process.env.JWT_SECRET || 'prismdeals_dev_secret_key_12345';

// Database setup
const dbPath = path.join(__dirname, '..', 'data', 'scraper.db');
const db = new sqlite3.Database(dbPath);
// WAL mode allows multiple concurrent readers/writers (parallel agent evals)
db.run('PRAGMA journal_mode=WAL;');
db.run('PRAGMA busy_timeout=5000;');

// Perform database schema migration on startup (non-destructive)
db.serialize(() => {
  // Create users table and seed default user if empty
  db.run(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL
    )
  `, (err) => {
    if (err) {
      console.error("Failed to create users table:", err);
      return;
    }
    db.get("SELECT COUNT(*) as count FROM users", (err, row) => {
      if (err) {
        console.error("Failed to query users count:", err);
        return;
      }
      if (row.count === 0) {
        const defaultEmail = process.env.DEFAULT_ADMIN_EMAIL || 'admin@prismdeals.local';
        let defaultPassword = process.env.DEFAULT_ADMIN_PASSWORD;
        if (process.env.NODE_ENV === 'production' && !defaultPassword) {
          console.error("FATAL: DEFAULT_ADMIN_PASSWORD environment variable is required in production to seed the default admin user!");
          process.exit(1);
        }
        if (!defaultPassword) {
          defaultPassword = 'password';
        }
        const saltRounds = 10;
        
        bcrypt.hash(defaultPassword, saltRounds, (err, hash) => {
          if (err) {
            console.error("Failed to hash default password:", err);
            return;
          }
          db.run("INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)", 
            [defaultEmail, hash, 'admin'], 
            (err) => {
              if (err) console.error("Failed to seed default admin user:", err);
              else console.log(`Seeded default admin user: ${defaultEmail}`);
            }
          );
        });
      }
    });
  });

  db.all("PRAGMA table_info(listings)", (err, rows) => {
    if (err) {
      console.error('Error reading table info:', err);
      return;
    }
    const columns = rows.map(r => r.name);
    
    if (!columns.includes('last_description_changed_at')) {
      db.run("ALTER TABLE listings ADD COLUMN last_description_changed_at TEXT", (err) => {
        if (err) console.error("Failed to add last_description_changed_at column:", err);
        else {
          console.log("Added column: last_description_changed_at");
          db.run("UPDATE listings SET last_description_changed_at = COALESCE(llm_processed_time, datetime('now', 'localtime'))");
        }
      });
    }
    
    if (!columns.includes('last_ai_evaluated_at')) {
      db.run("ALTER TABLE listings ADD COLUMN last_ai_evaluated_at TEXT", (err) => {
        if (err) console.error("Failed to add last_ai_evaluated_at column:", err);
        else {
          console.log("Added column: last_ai_evaluated_at");
          db.run("UPDATE listings SET last_ai_evaluated_at = llm_processed_time WHERE llm_processed = 1 AND llm_processed_time IS NOT NULL");
        }
      });
    }
  });
});

const query = (sql, params = []) => {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => {
      if (err) reject(err);
      else resolve(rows);
    });
  });
};

const run = (sql, params = []) => {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function(err) {
      if (err) reject(err);
      else resolve({ id: this.lastID, changes: this.changes });
    });
  });
};

const get = (sql, params = []) => {
  return new Promise((resolve, reject) => {
    db.get(sql, params, (err, row) => {
      if (err) reject(err);
      else resolve(row);
    });
  });
};

const isValidScrapeUrl = (urlStr) => {
  try {
    const parsed = new URL(urlStr);
    return (
      parsed.protocol === 'https:' &&
      (parsed.hostname === 'kleinanzeigen.de' || parsed.hostname === 'www.kleinanzeigen.de')
    );
  } catch {
    return false;
  }
};

const loginAttempts = new Map();
const loginRateLimiter = (req, res, next) => {
  const ip = req.ip;
  const now = Date.now();
  const windowMs = 15 * 60 * 1000; // 15 minutes
  const maxAttempts = 5;

  if (!loginAttempts.has(ip)) {
    loginAttempts.set(ip, []);
  }

  const attempts = loginAttempts.get(ip).filter(t => now - t < windowMs);
  attempts.push(now);
  loginAttempts.set(ip, attempts);

  if (attempts.length > maxAttempts) {
    return res.status(429).json({ error: 'Too many login attempts. Please try again in 15 minutes.' });
  }
  next();
};

// Periodic memory cleanup for inactive rate limiter IP records to prevent leaks
setInterval(() => {
  const now = Date.now();
  const windowMs = 15 * 60 * 1000;
  for (const [ip, attempts] of loginAttempts.entries()) {
    const active = attempts.filter(t => now - t < windowMs);
    if (active.length === 0) {
      loginAttempts.delete(ip);
    } else {
      loginAttempts.set(ip, active);
    }
  }
}, 15 * 60 * 1000).unref();

const authenticateToken = async (req, res, next) => {
  let token = null;
  if (req.headers.cookie) {
    const cookies = Object.fromEntries(
      req.headers.cookie.split(/;\s*/).map(c => {
        const parts = c.split('=');
        return [parts[0].trim(), parts.slice(1).join('=')];
      })
    );
    token = cookies['__Host-token'] || cookies.token;
  }

  if (!token) {
    return res.status(401).json({ error: 'Authentication required. No token provided.' });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    const user = await get("SELECT id, email, role FROM users WHERE id = ?", [decoded.userId]);
    if (!user) {
      return res.status(401).json({ error: 'User session invalid or user deleted.' });
    }
    req.user = user;
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid or expired authentication token.' });
  }
};


// Recalculates scores for all listings under a search item (normalized weight schema)
async function recalculateItemScores(searchId, scoringModelStr) {
  let scoringModel;
  try {
    scoringModel = JSON.parse(scoringModelStr);
  } catch (e) {
    console.error('Invalid scoring model JSON:', e);
    return;
  }

  const weights = scoringModel.weights || {};
  const listings = await query('SELECT id, extracted_facts FROM listings WHERE search_id = ?', [searchId]);

  for (const listing of listings) {
    let envelope = {};
    try {
      envelope = JSON.parse(listing.extracted_facts || '{}');
    } catch (e) {
      continue;
    }

    // Support nested envelope from AI analysis
    const facts = (envelope && envelope.criteria) ? envelope.criteria : envelope;

    let score = 0;
    for (const [criterionId, cfg] of Object.entries(weights)) {
      const factValue = facts[criterionId];
      if (factValue === undefined || factValue === null || factValue === 'unknown') continue;
      if (factValue === cfg.satisfied_if) {
        score += cfg.importance;
      }
    }

    score = Math.max(0, Math.min(100, score));
    await run('UPDATE listings SET niceness_score = ?, status = ? WHERE id = ?', [score, 'New', listing.id]);
  }
}

// Helper to execute Python AI Worker tasks (like drafting)
function runPythonWorker(args) {
  return new Promise((resolve, reject) => {
    const pythonExecutable = path.join(__dirname, '..', '.venv', 'bin', 'python3');
    const python = spawn(pythonExecutable, [path.join(__dirname, '..', 'scraper', 'agent_worker.py'), ...args]);
    let stdout = '';
    let stderr = '';
    
    python.stdout.on('data', (data) => stdout += data);
    python.stderr.on('data', (data) => stderr += data);
    
    python.on('close', (code) => {
      if (code === 0) {
        resolve(stdout.trim());
      } else {
        reject(new Error(stderr || `Python worker exited with code ${code}`));
      }
    });
  });
}

const distPath = path.join(__dirname, '..', 'frontend', 'dist');
if (fs.existsSync(distPath)) {
  app.use(express.static(distPath));
} else {
  app.use(express.static(path.join(__dirname, 'public')));
}
app.use(express.json());

// Auth: Login
app.post('/api/auth/login', loginRateLimiter, async (req, res) => {
  try {
    const { email, password } = req.body;
    if (!email || !password) {
      return res.status(400).json({ error: 'Email and password are required.' });
    }
    if (typeof email !== 'string' || typeof password !== 'string') {
      return res.status(400).json({ error: 'Email and password must be strings.' });
    }

    const user = await get("SELECT * FROM users WHERE email = ?", [email.toLowerCase().trim()]);
    
    // Always run bcrypt.compare to prevent timing attacks (user enumeration)
    const passwordHash = user ? user.password_hash : "$2b$10$VEPtO9A6YfW7.g.7/S9a9y9a9y9a9y9a9y9a9y9a9y9a9y9a9y9a9";
    const isMatch = await bcrypt.compare(password, passwordHash);

    if (!user || !isMatch) {
      return res.status(401).json({ error: 'Invalid email or password.' });
    }

    const token = jwt.sign({ userId: user.id }, JWT_SECRET, { expiresIn: '7d' });

    const isProd = process.env.NODE_ENV === 'production';
    res.cookie(isProd ? '__Host-token' : 'token', token, {
      httpOnly: true,
      secure: isProd,
      sameSite: 'strict',
      path: '/',
      maxAge: 7 * 24 * 60 * 60 * 1000 // 7 days
    });

    res.json({
      success: true,
      user: {
        email: user.email,
        role: user.role
      }
    });
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ error: 'Login failed due to a server error.' });
  }
});

// Auth: Logout
app.post('/api/auth/logout', (req, res) => {
  res.clearCookie('__Host-token', { path: '/' });
  res.clearCookie('token', { path: '/' });
  res.json({ success: true });
});

// Auth: Me
app.get('/api/auth/me', authenticateToken, (req, res) => {
  res.json({ user: req.user });
});

// Global API Auth Protection (applied to all subsequent /api/* routes)
app.use('/api', authenticateToken);

// API: Serve the external research agent prompt template
app.get('/api/external-prompt', (req, res) => {
  try {
    const promptPath = path.join(__dirname, '..', 'prompts', 'external_prompt.md');
    const content = fs.readFileSync(promptPath, 'utf8');
    res.type('text/plain').send(content);
  } catch (e) {
    res.status(500).json({ error: 'external_prompt.md not found' });
  }
});

// API: Get all listings
app.get('/api/listings', async (req, res) => {
  try {
    const { campaign_id, search_id } = req.query;
    let rows;
    if (search_id) {
      rows = await query(`
        SELECT l.*, s.name as item_name, c.name as campaign_name 
        FROM listings l 
        LEFT JOIN searches s ON l.search_id = s.id 
        LEFT JOIN campaigns c ON s.campaign_id = c.id
        WHERE l.search_id = ? 
        ORDER BY l.niceness_score DESC
      `, [search_id]);
    } else if (campaign_id) {
      rows = await query(`
        SELECT l.*, s.name as item_name, c.name as campaign_name 
        FROM listings l 
        LEFT JOIN searches s ON l.search_id = s.id 
        LEFT JOIN campaigns c ON s.campaign_id = c.id
        WHERE s.campaign_id = ? 
        ORDER BY l.niceness_score DESC
      `, [campaign_id]);
    } else {
      rows = await query(`
        SELECT l.*, s.name as item_name, c.name as campaign_name 
        FROM listings l 
        LEFT JOIN searches s ON l.search_id = s.id 
        LEFT JOIN campaigns c ON s.campaign_id = c.id
        ORDER BY l.niceness_score DESC
      `);
    }
    
    // Parse JSON string fields back to objects
    const listings = rows.map(r => ({
      ...r,
      llm_processed: !!r.llm_processed,
      full_info_obtained: !!r.full_info_obtained,
      extracted_facts: JSON.parse(r.extracted_facts || '{}'),
      details: JSON.parse(r.details || '{}'),
      images: JSON.parse(r.images || '[]')
    }));
    
    res.json(listings);
  } catch (error) {
    console.error('Error fetching listings:', error);
    res.status(500).json({ error: 'Failed to load listings data' });
  }
});

// API: Get campaigns
app.get('/api/campaigns', async (req, res) => {
  try {
    const rows = await query('SELECT * FROM campaigns');
    res.json(rows);
  } catch (error) {
    console.error('Error fetching campaigns:', error);
    res.status(500).json({ error: 'Failed to fetch campaigns' });
  }
});

// API: Create/Update campaign
app.post('/api/campaigns', async (req, res) => {
  try {
    const { id, name } = req.body;
    if (!name) {
      return res.status(400).json({ error: 'Missing campaign name' });
    }
    let campaignId = id;
    if (campaignId) {
      await run('UPDATE campaigns SET name = ? WHERE id = ?', [name, campaignId]);
    } else {
      const result = await run('INSERT INTO campaigns (name) VALUES (?)', [name]);
      campaignId = result.id;
    }
    res.json({ success: true, id: campaignId });
  } catch (error) {
    console.error('Error saving campaign:', error);
    res.status(500).json({ error: 'Failed to save campaign' });
  }
});

// API: Get search items
app.get('/api/search-urls', async (req, res) => {
  try {
    const rows = await query(`
      SELECT s.*, c.name as campaign_name, k.expert_knowledge, k.item_json 
      FROM searches s 
      LEFT JOIN campaigns c ON s.campaign_id = c.id
      LEFT JOIN knowledge_sets k ON s.knowledge_set_id = k.id
    `);
    res.json(rows.map(r => ({ 
      ...r, 
      enabled: !!r.enabled,
      item_json: JSON.parse(r.item_json || '{}')
    })));
  } catch (error) {
    console.error('Error fetching searches:', error);
    res.status(500).json({ error: 'Failed to load searches' });
  }
});

// API: Create / update single search item
app.post('/api/searches', async (req, res) => {
  try {
    const { id, campaign_id, name, url, knowledge_set_id } = req.body;
    if (!campaign_id || !name || !url) {
      return res.status(400).json({ error: 'Missing campaign_id, name, or url' });
    }

    if (!isValidScrapeUrl(url)) {
      return res.status(400).json({ error: 'Invalid search target URL. Only Kleinanzeigen URLs are allowed.' });
    }
    let searchId = id;
    const ksId = knowledge_set_id || null;
    if (searchId) {
      await run('UPDATE searches SET campaign_id = ?, name = ?, url = ?, knowledge_set_id = ? WHERE id = ?', [
        campaign_id, name, url, ksId, searchId
      ]);
    } else {
      const result = await run('INSERT INTO searches (campaign_id, name, url, knowledge_set_id) VALUES (?, ?, ?, ?)', [
        campaign_id, name, url, ksId
      ]);
      searchId = result.id;
    }
    res.json({ success: true, id: searchId });
  } catch (error) {
    console.error('Error saving search item:', error);
    res.status(500).json({ error: 'Failed to save search item' });
  }
});

// API: Delete search item
app.delete('/api/searches/:id', async (req, res) => {
  try {
    await run('DELETE FROM searches WHERE id = ?', [req.params.id]);
    res.json({ success: true });
  } catch (error) {
    console.error('Error deleting search:', error);
    res.status(500).json({ error: 'Failed to delete search' });
  }
});

// API: Get all reusable knowledge sets
app.get('/api/knowledge-sets', async (req, res) => {
  try {
    const rows = await query('SELECT * FROM knowledge_sets ORDER BY name ASC');
    res.json(rows.map(r => ({
      ...r,
      item_json: JSON.parse(r.item_json || '{}'),
      market_samples_json: JSON.parse(r.market_samples_json || '[]')
    })));
  } catch (error) {
    console.error('Error fetching knowledge sets:', error);
    res.status(500).json({ error: 'Failed to load knowledge sets' });
  }
});

// API: Create / update a knowledge set
app.post('/api/knowledge-sets', async (req, res) => {
  try {
    const { 
      id, name, expert_knowledge, item_json, market_memo, 
      good_reference_description, bad_reference_description, 
      market_samples_json, source_search_url, sample_timestamp 
    } = req.body;
    if (!name) {
      return res.status(400).json({ error: 'Missing knowledge set name' });
    }

    // Enforce planner schema (allowing fields with boolean, number, enum, tier, text)
    if (item_json && !item_json.fields) {
      const criteria = item_json.extraction_criteria || [];
      const weights = item_json.scoring_model?.weights || {};

      for (const c of criteria) {
        if (c.type !== 'boolean') {
          return res.status(400).json({ 
            error: `Legacy mixed-type criteria detected: Criterion '${c.id}' has type '${c.type}'. Only 'boolean' type is supported in legacy format. Use fields schema for typed fields.` 
          });
        }
      }

      for (const [cid, w] of Object.entries(weights)) {
        if (w && typeof w.satisfied_if !== 'boolean') {
          return res.status(400).json({
            error: `Legacy mixed-type criteria weights detected: Weight '${cid}' has satisfied_if value '${w.satisfied_if}' which is not a boolean.`
          });
        }
      }
    }


    let ksId = id;
    const jsonStr = JSON.stringify(item_json || {});
    const expertStr = expert_knowledge || '';
    const memoStr = market_memo || '';
    const goodRefStr = good_reference_description || '';
    const badRefStr = bad_reference_description || '';
    const samplesStr = JSON.stringify(market_samples_json || []);
    const sourceUrlStr = source_search_url || '';
    const timestampStr = sample_timestamp || '';

    if (ksId) {
      await run(`
        UPDATE knowledge_sets 
        SET name = ?, expert_knowledge = ?, item_json = ?, market_memo = ?, 
            good_reference_description = ?, bad_reference_description = ?, 
            market_samples_json = ?, source_search_url = ?, sample_timestamp = ? 
        WHERE id = ?
      `, [
        name, expertStr, jsonStr, memoStr, goodRefStr, badRefStr, samplesStr, sourceUrlStr, timestampStr, ksId
      ]);
    } else {
      const result = await run(`
        INSERT INTO knowledge_sets (
          name, expert_knowledge, item_json, market_memo, 
          good_reference_description, bad_reference_description, 
          market_samples_json, source_search_url, sample_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `, [
        name, expertStr, jsonStr, memoStr, goodRefStr, badRefStr, samplesStr, sourceUrlStr, timestampStr
      ]);
      ksId = result.id;
    }
    res.json({ success: true, id: ksId });
  } catch (error) {
    console.error('Error saving knowledge set:', error);
    res.status(500).json({ error: 'Failed to save knowledge set' });
  }
});

// API: Get 3-8 sample listings for a target search
app.get('/api/searches/:search_id/sample-listings', async (req, res) => {
  try {
    const searchId = req.params.search_id;
    // Get listings with title, details, detailed_description that belong to this search
    const rows = await query(`
      SELECT id, title, detailed_description, details 
      FROM listings 
      WHERE search_id = ? AND detailed_description IS NOT NULL AND detailed_description != '' 
      LIMIT 8
    `, [searchId]);
    
    // Format them
    const samples = rows.map(r => {
      let detailsText = '';
      try {
        const detailsObj = JSON.parse(r.details || '{}');
        detailsText = Object.entries(detailsObj).map(([k, v]) => `${k}: ${v}`).join(', ');
      } catch (e) {}
      return {
        id: r.id,
        title: r.title,
        description: r.detailed_description,
        details: detailsText
      };
    });
    
    res.json(samples);
  } catch (error) {
    console.error('Error fetching sample listings:', error);
    res.status(500).json({ error: 'Failed to fetch sample listings' });
  }
});

// API: Serve external Prompt A (Market Interpreter) template
app.get('/api/prompts/market', (req, res) => {
  try {
    const promptPath = path.join(__dirname, '..', 'prompts', 'external_prompt_market.md');
    const content = fs.readFileSync(promptPath, 'utf8');
    res.type('text/plain').send(content);
  } catch (e) {
    res.status(500).json({ error: 'external_prompt_market.md not found' });
  }
});

// API: Serve external Prompt B (Profile Synthesizer) template
app.get('/api/prompts/profile', (req, res) => {
  try {
    const promptPath = path.join(__dirname, '..', 'prompts', 'external_prompt_profile.md');
    const content = fs.readFileSync(promptPath, 'utf8');
    res.type('text/plain').send(content);
  } catch (e) {
    res.status(500).json({ error: 'external_prompt_profile.md not found' });
  }
});

// API: Serve external Prompt Research template
app.get('/api/prompts/research', (req, res) => {
  try {
    const promptPath = path.join(__dirname, '..', 'prompts', 'external_prompt_research.md');
    const content = fs.readFileSync(promptPath, 'utf8');
    res.type('text/plain').send(content);
  } catch (e) {
    res.status(500).json({ error: 'external_prompt_research.md not found' });
  }
});

// API: Delete a knowledge set
app.delete('/api/knowledge-sets/:id', async (req, res) => {
  try {
    await run('DELETE FROM knowledge_sets WHERE id = ?', [req.params.id]);
    res.json({ success: true });
  } catch (error) {
    console.error('Error deleting knowledge set:', error);
    res.status(500).json({ error: 'Failed to delete knowledge set' });
  }
});

// API: Live target URL preview count checking
app.post('/api/searches/preview', (req, res) => {
  const { url } = req.body;
  if (!url) {
    return res.status(400).json({ error: 'Missing target URL' });
  }

  if (!isValidScrapeUrl(url)) {
    return res.status(400).json({ error: 'Invalid search target URL. Only Kleinanzeigen URLs are allowed.' });
  }

  const pythonExecutable = path.join(__dirname, '..', '.venv', 'bin', 'python3');
  const scriptPath = path.join(__dirname, '..', 'scraper', 'main.py');
  
  const python = spawn(pythonExecutable, [scriptPath, '--mode', 'preview', '--urls', url]);
  
  let stdout = '';
  let stderr = '';
  
  python.stdout.on('data', (data) => stdout += data);
  python.stderr.on('data', (data) => stderr += data);
  
  python.on('close', (code) => {
    if (code === 0) {
      const match = stdout.match(/__PREVIEW_COUNT__:(\d+)/);
      if (match) {
        return res.json({ count: parseInt(match[1], 10) });
      }
      const errMatch = stdout.match(/__PREVIEW_ERROR__:(.+)/);
      return res.status(400).json({ error: errMatch ? errMatch[1] : 'Could not parse listing count from page.' });
    } else {
      console.error('Preview error:', stderr || stdout);
      return res.status(500).json({ error: 'Headless browser check failed.' });
    }
  });
});

// API: Recalculate search scores based on updated item JSON scoring weights
app.post('/api/searches/recalculate', async (req, res) => {
  try {
    const { search_id, item_json } = req.body;
    
    await run('UPDATE searches SET item_json = ? WHERE id = ?', [
      JSON.stringify(item_json),
      search_id
    ]);
    
    const scoringModel = item_json.scoring_model || {};
    await recalculateItemScores(search_id, JSON.stringify(scoringModel));
    res.json({ success: true });
  } catch (error) {
    console.error('Error recalculating search item scores:', error);
    res.status(500).json({ error: 'Failed to update and recalculate scores' });
  }
});

// API: Chrome Extension Chat & Conversation Sync
app.post('/api/chats/sync', async (req, res) => {
  try {
    const { listing_id, messages } = req.body;
    if (!listing_id || !messages || !Array.isArray(messages)) {
      return res.status(400).json({ error: 'Invalid payload' });
    }
    
    // Ensure listing exists in database. If not, maybe create a placeholder
    const listing = await get('SELECT id FROM listings WHERE id = ?', [listing_id]);
    if (!listing) {
      await run(`
        INSERT INTO listings (id, title, status)
        VALUES (?, ?, 'Contacted')
      `, [listing_id, `Listing ID: ${listing_id}`]);
    }
    
    const stmt = db.prepare(`
      INSERT OR REPLACE INTO messages (id, listing_id, sender_name, sender_initials, is_outbound, message_text, message_date)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    
    for (const msg of messages) {
      stmt.run(
        msg.id,
        listing_id,
        msg.sender_name || null,
        msg.sender_initials || null,
        msg.is_outbound ? 1 : 0,
        msg.message_text || '',
        msg.message_date || null
      );
    }
    stmt.finalize();
    
    // Set status to "Negotiating" if chat sync happened
    await run("UPDATE listings SET status = 'Negotiating' WHERE id = ? AND (status = 'New' OR status = 'Contacted')", [listing_id]);
    
    // Run AI analysis on conversation to resolve unknowns
    try {
      await runPythonWorker(['analyze', listing_id]);
      console.log(`Analyzed conversation for listing ${listing_id}`);
    } catch (e) {
      console.error(`Conversation analysis error for listing ${listing_id}:`, e);
    }
    
    res.json({ success: true });
  } catch (error) {
    console.error('Error syncing chats:', error);
    res.status(500).json({ error: 'Failed to sync chats' });
  }
});

// API: Retrieve messages for a listing
app.get('/api/chats/:listing_id', async (req, res) => {
  try {
    const rows = await query('SELECT * FROM messages WHERE listing_id = ? ORDER BY message_date ASC', [req.params.listing_id]);
    res.json(rows.map(r => ({ ...r, is_outbound: !!r.is_outbound })));
  } catch (error) {
    console.error('Error retrieving messages:', error);
    res.status(500).json({ error: 'Failed to load messages' });
  }
});

// API: Generate AI Outreach Draft Reply for a Listing
app.post('/api/listings/draft', async (req, res) => {
  try {
    const { listing_id } = req.body;
    
    // Fetch listing & profile data
    const listing = await get('SELECT * FROM listings WHERE id = ?', [listing_id]);
    if (!listing) {
      return res.status(404).json({ error: 'Listing not found' });
    }
    
    if (!listing.profile_id) {
      return res.status(400).json({ error: 'No profile associated with this listing' });
    }
    
    const profile = await get('SELECT * FROM profiles WHERE id = ?', [listing.profile_id]);
    
    // Spawn Python AI Worker to generate the tailored draft outreach
    const result = await runPythonWorker(['draft', listing_id]);
    
    res.json({ draft: result });
  } catch (error) {
    console.error('Error drafting outreach:', error);
    res.status(500).json({ error: error.message || 'Failed to generate draft outreach' });
  }
});

// API: Get current schedule config
app.get('/api/schedule', (req, res) => {
  try {
    const configPath = path.join(__dirname, '..', 'data', 'schedule_config.json');
    const defaultConfig = {
      interval: 10,
      autoAiEval: true,
      fullFetchOnStartup: false,
      delayBetweenPages: 0.25,
      delayBetweenListings: 0.25
    };
    if (!fs.existsSync(configPath)) {
      fs.writeFileSync(configPath, JSON.stringify(defaultConfig, null, 2));
    }
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    res.json({ ...defaultConfig, ...config });
  } catch (error) {
    console.error('Error reading schedule config:', error);
    res.status(500).json({ error: 'Failed to load schedule config' });
  }
});

// API: Save schedule config and dynamically update timers
app.post('/api/schedule', (req, res) => {
  try {
    const { interval, autoAiEval, fullFetchOnStartup, delayBetweenPages, delayBetweenListings } = req.body;
    if (interval === undefined) {
      return res.status(400).json({ error: 'Missing interval field' });
    }

    const parsedInterval = parseInt(interval, 10);
    if (isNaN(parsedInterval) || parsedInterval < 1) {
      return res.status(400).json({ error: 'Interval must be a positive integer' });
    }
    
    let pagesDelay = parseFloat(delayBetweenPages !== undefined ? delayBetweenPages : 0.25);
    let listingsDelay = parseFloat(delayBetweenListings !== undefined ? delayBetweenListings : 0.25);
    if (isNaN(pagesDelay) || pagesDelay < 0) {
      pagesDelay = 0.25;
    }
    if (isNaN(listingsDelay) || listingsDelay < 0) {
      listingsDelay = 0.25;
    }
    
    const configPath = path.join(__dirname, '..', 'data', 'schedule_config.json');
    const newConfig = {
      interval: parsedInterval,
      autoAiEval: !!autoAiEval,
      fullFetchOnStartup: !!fullFetchOnStartup,
      delayBetweenPages: pagesDelay,
      delayBetweenListings: listingsDelay
    };
    
    fs.writeFileSync(configPath, JSON.stringify(newConfig, null, 2));
    
    // Apply changes dynamically
    setupScheduledScraping();
    
    res.json({ success: true, config: newConfig });
  } catch (error) {
    console.error('Error saving schedule config:', error);
    res.status(500).json({ error: 'Failed to save schedule config' });
  }
});

let activeScraperProcess = null;
const activeWorkerProcesses = new Map(); // listing_id -> child process

// API: Check scraper execution status and progress
app.get('/api/scrape/status', (req, res) => {
  const progressFile = path.join(__dirname, '..', 'data', 'scraper_progress.json');
  let progress = { phase: 'idle', current: 0, total: 0, status: 'No active scraping session' };
  
  if (activeScraperProcess !== null) {
    if (fs.existsSync(progressFile)) {
      try {
        progress = JSON.parse(fs.readFileSync(progressFile, 'utf8'));
      } catch (e) {
        progress = { phase: 'running', current: 0, total: 0, status: 'Active scraping session running...' };
      }
    } else {
      progress = { phase: 'running', current: 0, total: 0, status: 'Active scraping session running...' };
    }
  } else {
    if (fs.existsSync(progressFile)) {
      try {
        const fileData = JSON.parse(fs.readFileSync(progressFile, 'utf8'));
        if (Date.now() / 1000 - fileData.timestamp > 600) {
          progress = { phase: 'idle', current: 0, total: 0, status: 'Scraper is idle' };
        } else {
          progress = fileData;
        }
      } catch (e) {
        // Ignore
      }
    }
  }
  
  res.json({
    active: activeScraperProcess !== null,
    progress
  });
});

// API: Get recent scraper logs for live display
app.get('/api/logs', (req, res) => {
  const logFile = path.join(__dirname, '..', 'data', 'scraper.log');
  if (!fs.existsSync(logFile)) {
    return res.json({ logs: 'No logs available yet.' });
  }
  
  try {
    const logsContent = fs.readFileSync(logFile, 'utf8');
    const lines = logsContent.split('\n');
    const lastLines = lines.slice(-80).join('\n');
    res.json({ logs: lastLines });
  } catch (e) {
    res.status(500).json({ error: 'Failed to read logs' });
  }
});

// API: Trigger scraper execution (asynchronous data fetching)
app.post('/api/scrape', (req, res) => {
  try {
    if (activeScraperProcess !== null) {
      return res.status(400).json({ error: 'Scraper is already running' });
    }

    const { interval, campaignId } = req.body;
    
    if (interval) {
      const configPath = path.join(__dirname, '..', 'data', 'schedule_config.json');
      let currentConfig = {};
      try {
        if (fs.existsSync(configPath)) {
          currentConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        }
      } catch (e) {}
      const updatedConfig = {
        ...currentConfig,
        interval: parseInt(interval, 10)
      };
      fs.writeFileSync(configPath, JSON.stringify(updatedConfig, null, 2));
      setupScheduledScraping();
    }
    
    // Clear old progress file
    const progressFile = path.join(__dirname, '..', 'data', 'scraper_progress.json');
    if (fs.existsSync(progressFile)) {
      try { fs.unlinkSync(progressFile); } catch (e) {}
    }
    
    // Spawn scraper execution in 'scrape' mode
    const pythonExecutable = path.join(__dirname, '..', '.venv', 'bin', 'python3');
    const args = [
      path.join(__dirname, '..', 'scraper', 'main.py'),
      '--mode', 'scrape'
    ];
    if (campaignId) {
      args.push('--campaign-id', String(campaignId));
    }
    const python = spawn(pythonExecutable, args, {
      env: { ...process.env }
    });
    
    activeScraperProcess = python;
    console.log('Background scraper spawned');
    
    python.stdout.on('data', (data) => console.log(`Python stdout: ${data}`));
    python.stderr.on('data', (data) => console.error(`Python stderr: ${data}`));
    
    python.on('close', (code) => {
      console.log(`Python scraper exited with code ${code}`);
      activeScraperProcess = null;
    });
    
    res.json({ success: true, message: 'Scraping started' });
    
  } catch (error) {
    console.error('Error triggering scrape:', error);
    res.status(500).json({ error: 'Failed to trigger scraping' });
  }
});

// API: Trigger deep description updates for all existing listings
app.post('/api/scrape/update-all', (req, res) => {
  try {
    if (activeScraperProcess !== null) {
      return res.status(400).json({ error: 'Scraper or update process is already running' });
    }
    
    const { campaignId } = req.body || {};
    
    // Clear old progress file
    const progressFile = path.join(__dirname, '..', 'data', 'scraper_progress.json');
    if (fs.existsSync(progressFile)) {
      try { fs.unlinkSync(progressFile); } catch (e) {}
    }
    
    // Spawn scraper execution in 'update-all' mode
    const pythonExecutable = path.join(__dirname, '..', '.venv', 'bin', 'python3');
    const args = [
      path.join(__dirname, '..', 'scraper', 'main.py'),
      '--mode', 'update-all'
    ];
    if (campaignId) {
      args.push('--campaign-id', String(campaignId));
    }
    const python = spawn(pythonExecutable, args, {
      env: { ...process.env }
    });
    
    activeScraperProcess = python;
    console.log('Background deep update scraper spawned');
    
    python.stdout.on('data', (data) => console.log(`Python stdout: ${data}`));
    python.stderr.on('data', (data) => console.error(`Python stderr: ${data}`));
    
    python.on('close', (code) => {
      console.log(`Python scraper exited with code ${code}`);
      activeScraperProcess = null;
    });
    
    res.json({ success: true, message: 'Deep description update started' });
    
  } catch (error) {
    console.error('Error triggering deep update:', error);
    res.status(500).json({ error: 'Failed to trigger deep description update' });
  }
});

// API: Trigger a targeted scraper execution for a specific search ID
app.post('/api/searches/:search_id/scrape', async (req, res) => {
  try {
    const searchId = req.params.search_id;
    const search = await get('SELECT * FROM searches WHERE id = ?', [searchId]);
    if (!search) {
      return res.status(404).json({ error: 'Search target not found' });
    }

    if (activeScraperProcess !== null) {
      return res.status(400).json({ error: 'Scraper is already running' });
    }

    // Clear old progress file
    const progressFile = path.join(__dirname, '..', 'data', 'scraper_progress.json');
    if (fs.existsSync(progressFile)) {
      try { fs.unlinkSync(progressFile); } catch (e) {}
    }

    const pythonExecutable = path.join(__dirname, '..', '.venv', 'bin', 'python3');
    const python = spawn(pythonExecutable, [
      path.join(__dirname, '..', 'scraper', 'main.py'),
      '--mode', 'scrape',
      '--urls', search.url,
      '--search-id', String(search.id),
      '--max-listings', '5'
    ], {
      env: { ...process.env }
    });

    activeScraperProcess = python;
    console.log(`Background targeted scraper spawned for search ID ${searchId}`);

    python.stdout.on('data', (data) => console.log(`Python stdout: ${data}`));
    python.stderr.on('data', (data) => console.error(`Python stderr: ${data}`));

    python.on('close', (code) => {
      console.log(`Python targeted scraper exited with code ${code}`);
      activeScraperProcess = null;
    });

    res.json({ success: true, message: 'Targeted scraping started' });

  } catch (error) {
    console.error('Error triggering targeted scrape:', error);
    res.status(500).json({ error: 'Failed to trigger targeted scraping' });
  }
});

// API: Which listings currently have an AI eval running
app.get('/api/process/active', (req, res) => {
  res.json({ active: Array.from(activeWorkerProcesses.keys()) });
});

// API: Trigger AI matching & scoring interpretation
app.post('/api/process', (req, res) => {
  try {
    const { listing_id, campaignId } = req.body || {};
    const key = listing_id ? String(listing_id) : '__all__';

    // Only guard per-listing duplicates; __all__ (bulk) is always allowed
    if (listing_id && activeWorkerProcesses.has(key)) {
      return res.status(409).json({ error: 'Evaluation already running for this listing' });
    }

    const pythonExecutable = path.join(__dirname, '..', '.venv', 'bin', 'python3');
    const args = [
      path.join(__dirname, '..', 'scraper', 'main.py'),
      '--mode', 'process'
    ];
    if (listing_id) {
      args.push('--listing-id', String(listing_id));
    }
    if (campaignId) {
      args.push('--campaign-id', String(campaignId));
    }

    const python = spawn(pythonExecutable, args, { env: { ...process.env } });
    activeWorkerProcesses.set(key, python);

    python.stdout.on('data', (data) => console.log(`AI worker stdout: ${data}`));
    python.stderr.on('data', (data) => console.error(`AI worker stderr: ${data}`));

    python.on('close', (code) => {
      console.log(`AI worker exited with code ${code}`);
      activeWorkerProcesses.delete(key);
      res.json({ success: code === 0, message: 'AI processing completed' });
    });

  } catch (error) {
    console.error('Error triggering AI process:', error);
    res.status(500).json({ error: 'Failed to trigger AI matching' });
  }
});

// API: Get current login session status
app.get('/api/session-status', (req, res) => {
  try {
    const statusPath = path.join(__dirname, '..', 'data', 'session_status.json');
    if (fs.existsSync(statusPath)) {
      const data = JSON.parse(fs.readFileSync(statusPath, 'utf8'));
      return res.json(data);
    }
    res.json({ email: null });
  } catch (error) {
    console.error('Error fetching session status:', error);
    res.status(500).json({ error: 'Failed to read session status' });
  }
});

// API: Trigger interactive manual login session
app.post('/api/login-session', (req, res) => {
  try {
    const pythonExecutable = path.join(__dirname, '..', '.venv', 'bin', 'python3');
    const python = spawn(pythonExecutable, [
      path.join(__dirname, '..', 'scraper', 'main.py'),
      '--mode', 'scrape',
      '--urls', 'https://www.kleinanzeigen.de/m-meine-anzeigen.html?tab=PROJECTS'
    ], {
      env: {
        ...process.env,
        INTERACTIVE_LOGIN: "1"
      }
    });

    python.stdout.on('data', (data) => console.log(`Login process: ${data}`));
    python.stderr.on('data', (data) => console.error(`Login error: ${data}`));

    python.on('close', (code) => {
      console.log(`Interactive login process exited with code ${code}`);
      res.json({ success: code === 0 });
    });
  } catch (error) {
    console.error('Error launching login session:', error);
    res.status(500).json({ error: 'Failed to trigger login process' });
  }
});

// Serve UI pages
app.get('/', (req, res) => {
  const distIndex = path.join(__dirname, '..', 'frontend', 'dist', 'index.html');
  if (fs.existsSync(distIndex)) {
    res.sendFile(distIndex);
  } else {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
  }
});

let scheduledScrapeInterval = null;
let startupScrapeTimeout = null;

// Scheduled Scrape configuration helper
function setupScheduledScraping() {
  try {
    const configPath = path.join(__dirname, '..', 'data', 'schedule_config.json');
    const defaultConfig = {
      interval: 10,
      autoAiEval: true,
      fullFetchOnStartup: false
    };
    
    if (!fs.existsSync(configPath)) {
      fs.writeFileSync(configPath, JSON.stringify(defaultConfig, null, 2));
    }
    
    let config = defaultConfig;
    try {
      const fileConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      config = { ...defaultConfig, ...fileConfig };
    } catch (e) {
      console.error('Error parsing schedule config, overwriting with default:', e);
      fs.writeFileSync(configPath, JSON.stringify(defaultConfig, null, 2));
    }

    const intervalMinutes = parseInt(config.interval, 10) || 10;
    const fullFetchOnStartup = !!config.fullFetchOnStartup;
    
    console.log(`Scheduled scraping setup: every ${intervalMinutes} minutes.`);
    
    // Clear any existing timers
    if (startupScrapeTimeout) {
      clearTimeout(startupScrapeTimeout);
      startupScrapeTimeout = null;
    }
    if (scheduledScrapeInterval) {
      clearInterval(scheduledScrapeInterval);
      scheduledScrapeInterval = null;
    }
    
    if (fullFetchOnStartup) {
      console.log('Immediate startup crawl scheduled in 10s');
      startupScrapeTimeout = setTimeout(() => {
        runScraper();
      }, 10000);
    } else {
      console.log('Skipping immediate startup crawl (fullFetchOnStartup is false)');
    }
    
    scheduledScrapeInterval = setInterval(() => {
      runScraper();
    }, intervalMinutes * 60 * 1000);
    
  } catch (error) {
    console.error('Error setting up scheduled scraping:', error);
  }
}

function runScraper() {
  console.log('Running scheduled scrape...');
  
  let autoAiEval = true;
  try {
    const configPath = path.join(__dirname, '..', 'data', 'schedule_config.json');
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      if (config.autoAiEval !== undefined) {
        autoAiEval = !!config.autoAiEval;
      }
    }
  } catch (e) {
    console.error('Failed to read config in runScraper:', e);
  }
  
  const mode = autoAiEval ? 'both' : 'scrape';
  console.log(`Scheduled scrape running in mode: ${mode}`);

  const pythonExecutable = path.join(__dirname, '..', '.venv', 'bin', 'python3');
  const python = spawn(pythonExecutable, [
    path.join(__dirname, '..', 'scraper', 'main.py'),
    '--mode', mode
  ], {
    env: { ...process.env }
  });
  python.stdout.on('data', (data) => console.log(`Python stdout: ${data}`));
  python.stderr.on('data', (data) => console.error(`Python stderr: ${data}`));
}

app.listen(port, () => {
  console.log(`Multi-Domain Scraper App listening at http://localhost:${port}`);
  setupScheduledScraping();
});