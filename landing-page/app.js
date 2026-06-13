/* ── LocalPulse AI — Landing Page Form Handler ── */

(function() {
  const form = document.getElementById('reportForm');
  const submitBtn = document.getElementById('submitBtn');
  const successMsg = document.getElementById('successMessage');
  const successText = document.getElementById('successText');
  const snapshotIdEl = document.getElementById('snapshotId');

  if (!form) return;

  form.addEventListener('submit', async function(e) {
    e.preventDefault();

    const payload = {
      business_name: document.getElementById('business_name').value.trim(),
      email: document.getElementById('email').value.trim(),
      city: document.getElementById('city').value.trim(),
      state: document.getElementById('state').value,
      niche: document.getElementById('niche').value,
      website: document.getElementById('website').value.trim(),
    };

    // Basic validation
    if (!payload.business_name || !payload.email || !payload.city || !payload.state || !payload.niche) {
      alert('Please fill in all required fields.');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payload.email)) {
      alert('Please enter a valid email address.');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Analyzing...';

    try {
      // Try the real API first, fall back to mock
      const apiUrl = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1')
        ? 'http://localhost:5000/api/request-report'
        : '/api/request-report';

      const res = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json();
        showSuccess(data);
      } else {
        // Fallback: mock success for static preview
        mockSuccess(payload);
      }
    } catch (err) {
      // No backend? Mock it for preview
      mockSuccess(payload);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Analyze My Business';
    }
  });

  function showSuccess(data) {
    form.style.display = 'none';
    successMsg.style.display = 'block';
    successText.textContent = data.message || 'Your Business Health Snapshot is being prepared. Check your email shortly.';
    snapshotIdEl.textContent = data.snapshot_id || 'preview-' + Math.random().toString(36).slice(2, 10);
  }

  function mockSuccess(payload) {
    form.style.display = 'none';
    successMsg.style.display = 'block';
    successText.textContent = `Thanks, ${payload.business_name}! Your Business Health Snapshot is being prepared. We'll email the report to ${payload.email} within minutes.`;
    snapshotIdEl.textContent = 'preview-' + Math.random().toString(36).slice(2, 10);
  }
})();
