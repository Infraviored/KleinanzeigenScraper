const express = require('express');
const { spawn } = require('child_process');
const app = express();
app.use(express.json());
app.use('/api', (req,res,next)=>next());
function runPlanner(args, req = null) {
  return new Promise((resolve, reject) => {
    const python = spawn('bash', ['-c', 'sleep 2; echo "__ROUTE_PREVIEW__:{}"']);
    if (req) req.on('close', () => python.kill());
    let stdout = '', stderr = '';
    python.stdout.on('data', d => { stdout += d; });
    python.stderr.on('data', d => { stderr += d; });
    python.on('error', reject);
    python.on('close', code => resolve({ code, stdout, stderr }));
  });
}
app.post('/api/route-searches/preview', async (req, res) => {
  const r = await runPlanner([], req);
  console.log('RESULT', JSON.stringify(r));
  res.json(r);
});
const s = app.listen(4599, () => console.log('up'));
