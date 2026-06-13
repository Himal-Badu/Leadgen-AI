(function() {
    const form = document.getElementById('reportForm');
    const submitBtn = document.getElementById('submitBtn');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnSpinner = submitBtn.querySelector('.btn-spinner');
    const successMessage = document.getElementById('successMessage');
    const errorMessage = document.getElementById('errorMessage');
    const successText = document.getElementById('successText');
    const snapshotIdEl = document.getElementById('snapshotId');
    const statusBadge = document.getElementById('statusBadge');
    const checkStatusBtn = document.getElementById('checkStatusBtn');

    let currentSnapshotId = null;

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        clearErrors();
        hideMessages();

        const payload = {
            business_name: document.getElementById('business_name').value.trim(),
            email: document.getElementById('email').value.trim(),
            city: document.getElementById('city').value.trim(),
            state: document.getElementById('state').value,
            niche: document.getElementById('niche').value,
            website: document.getElementById('website').value.trim(),
        };

        // Client-side validation
        const required = ['business_name', 'email', 'city', 'state', 'niche'];
        let hasError = false;
        for (const key of required) {
            if (!payload[key]) {
                showError(key, 'This field is required');
                hasError = true;
            }
        }
        if (payload.email && !isValidEmail(payload.email)) {
            showError('email', 'Please enter a valid email address');
            hasError = true;
        }
        if (hasError) return;

        setLoading(true);

        try {
            const res = await fetch('/api/request-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();

            if (data.success) {
                currentSnapshotId = data.snapshot_id;
                successText.textContent = data.message;
                snapshotIdEl.textContent = data.snapshot_id;
                statusBadge.textContent = 'pending';
                statusBadge.className = 'badge pending';
                form.style.display = 'none';
                successMessage.style.display = 'block';
            } else {
                showGlobalError(data.error || 'Something went wrong. Please try again.');
            }
        } catch (err) {
            showGlobalError('Network error. Please check your connection and try again.');
        } finally {
            setLoading(false);
        }
    });

    checkStatusBtn.addEventListener('click', async function() {
        if (!currentSnapshotId) return;
        checkStatusBtn.textContent = 'Checking...';
        checkStatusBtn.disabled = true;

        try {
            const res = await fetch(`/api/status/${currentSnapshotId}`);
            const data = await res.json();
            if (data.success) {
                statusBadge.textContent = data.status;
                statusBadge.className = 'badge ' + data.status;

                let detail = '';
                if (data.status === 'ready_for_outreach') {
                    detail = ' Your report is ready! Check your email shortly.';
                } else if (data.status === 'completed') {
                    detail = ' Report generated. Finalizing deliverables...';
                } else if (data.status === 'pending') {
                    detail = ' Still gathering data. Check back in a minute.';
                }
                successText.textContent = (successText.textContent.split('.')[0] || successText.textContent) + '.' + detail;
            }
        } catch (err) {
            console.error(err);
        } finally {
            checkStatusBtn.textContent = 'Check Status';
            checkStatusBtn.disabled = false;
        }
    });

    function showError(fieldId, msg) {
        const el = document.getElementById(fieldId);
        const errEl = document.getElementById('err-' + fieldId);
        if (el) el.classList.add('error');
        if (errEl) errEl.textContent = msg;
    }

    function clearErrors() {
        document.querySelectorAll('.error-msg').forEach(el => el.textContent = '');
        document.querySelectorAll('input, select').forEach(el => el.classList.remove('error'));
    }

    function showGlobalError(msg) {
        errorMessage.querySelector('#errorText').textContent = msg;
        errorMessage.style.display = 'block';
    }

    function hideMessages() {
        successMessage.style.display = 'none';
        errorMessage.style.display = 'none';
    }

    function setLoading(isLoading) {
        submitBtn.disabled = isLoading;
        btnText.style.display = isLoading ? 'none' : 'inline';
        btnSpinner.style.display = isLoading ? 'inline' : 'none';
    }

    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }
})();
