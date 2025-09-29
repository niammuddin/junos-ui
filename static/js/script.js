document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide alert setelah 5 detik
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            if (alert.classList.contains('show')) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        }, 5000);
    });

    // Form validation enhancement
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            const username = this.querySelector('#username');
            const password = this.querySelector('#password');
            let isValid = true;

            // Validasi client-side
            if (username.value.trim().length < 3) {
                showError(username, 'Username minimal 3 karakter');
                isValid = false;
            } else {
                clearError(username);
            }

            if (password.value.length < 8) {
                showError(password, 'Password minimal 8 karakter');
                isValid = false;
            } else {
                clearError(password);
            }

            if (!isValid) {
                e.preventDefault();
            }
        });
    }

    function showError(input, message) {
        clearError(input);
        input.classList.add('is-invalid');
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'invalid-feedback';
        errorDiv.textContent = message;
        input.parentNode.appendChild(errorDiv);
    }

    function clearError(input) {
        input.classList.remove('is-invalid');
        const existingError = input.parentNode.querySelector('.invalid-feedback');
        if (existingError) {
            existingError.remove();
        }
    }

    // Tambahan: Prevent multiple form submissions
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function() {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Loading...';
                
                // Re-enable after 3 seconds jika ada error
                setTimeout(() => {
                    submitBtn.disabled = false;
                    if (form.id === 'loginForm') {
                        submitBtn.innerHTML = '<i class="fas fa-sign-in-alt me-2"></i>Login';
                    }
                }, 3000);
            }
        });
    });
});