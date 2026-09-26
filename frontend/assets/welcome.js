const btnGetStarted=document.getElementById("btn-get-started");
let toastTimer;function showToast(text){const node=document.getElementById("toast-pill");node.textContent=text;node.classList.add("show");clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove("show"),3500);}
    // =========================================================
    // SUPABASE GOOGLE AUTHENTICATION & LANDING FLOW
    // =========================================================
    let supabaseClient = null;
    try {
      const config = await fetch('/api/config').then(r => r.json());
      if (config.supabase_url && config.supabase_key && window.supabase) supabaseClient = window.supabase.createClient(config.supabase_url, config.supabase_key);
    } catch (_) { /* Existing login error state handles unavailable configuration. */ }

    const stateChecking = document.getElementById('hero-state-checking');
    const stateLoggedOut = document.getElementById('hero-state-logged-out');
    const stateLoggedIn = document.getElementById('hero-state-logged-in');
    const heroUserAvatar = document.getElementById('hero-user-avatar');
    const heroUserFirstname = document.getElementById('hero-user-firstname');
    const btnHeroGoogleLogin = document.getElementById('btn-hero-google-login');
    const btnHeroLogout = document.getElementById('btn-hero-logout');

    let currentUser = null;

    function extractUserData(user) {
      if (!user) return { firstName: '', fullName: '', email: '', avatarUrl: '' };
      const meta = user.user_metadata || {};
      const email = user.email || '';

      let fullName = meta.full_name || meta.name || '';
      if (!fullName && email) {
        fullName = email.split('@')[0];
      }
      if (!fullName) fullName = 'User';

      let firstName = meta.given_name || meta.first_name || '';
      if (!firstName && fullName) {
        firstName = fullName.trim().split(' ')[0];
      }
      if (!firstName && email) {
        const local = email.split('@')[0];
        firstName = local.charAt(0).toUpperCase() + local.slice(1);
      }
      if (!firstName) firstName = 'User';

      const avatarUrl = meta.avatar_url || meta.picture || `https://ui-avatars.com/api/?name=${encodeURIComponent(firstName)}&background=4834D4&color=fff`;

      return { firstName, fullName, email, avatarUrl };
    }

    function showLoginScreen() {
      currentUser = null;
      if (stateChecking) stateChecking.style.display = 'none';
      if (stateLoggedIn) stateLoggedIn.style.display = 'none';
      if (stateLoggedOut) stateLoggedOut.style.display = 'flex';
      if (heroUserFirstname) heroUserFirstname.textContent = '';
      if (heroUserAvatar) heroUserAvatar.src = '';
    }

    function showAuthenticatedWelcome(user) {
      currentUser = user;
      const userData = extractUserData(user);
      if (stateChecking) stateChecking.style.display = 'none';
      if (stateLoggedOut) stateLoggedOut.style.display = 'none';
      if (stateLoggedIn) stateLoggedIn.style.display = 'flex';
      if (heroUserFirstname) heroUserFirstname.textContent = userData.firstName;
      if (heroUserAvatar) {
        heroUserAvatar.src = userData.avatarUrl;
        heroUserAvatar.alt = userData.fullName;
      }
    }

    function clearAuthenticatedState() {
      currentUser = null;
      try {
        localStorage.removeItem('jerryys_ai_history');
      } catch (_) {}
    }

    async function handleGoogleLogin() {
      if (!supabaseClient) {
        showToast('Supabase client not initialized');
        return;
      }
      try {
        const { error } = await supabaseClient.auth.signInWithOAuth({
          provider: "google",
          options: {
            redirectTo: window.location.origin
          }
        });
        if (error) {

          showToast('Login error: ' + error.message);
        }
      } catch (err) {

        showToast('Could not open Google login.');
      }
    }

    if (btnHeroGoogleLogin) btnHeroGoogleLogin.addEventListener('click', handleGoogleLogin);

    async function handleLogout() {
      try {
        if (supabaseClient) {
          await supabaseClient.auth.signOut();
        }
      } catch (err) {

      } finally {
        clearAuthenticatedState();
        showLoginScreen();
        showToast('Signed out');
      }
    }

    if (btnHeroLogout) btnHeroLogout.addEventListener('click', handleLogout);

    // EXPLORE MODEL: Navigate directly to /chat route
    if (btnGetStarted) {
      btnGetStarted.addEventListener('click', (e) => {
        e.preventDefault();
        try { sessionStorage.removeItem('loopstackReady'); } catch (_) {}
        window.location.href = '/chat';
      });
    }

    const btnOpenKurama1 = document.getElementById('loopstack-hero-btn');
    const btnOpenKurama2 = document.getElementById('kurama-status-toggle');
    if (btnOpenKurama1) btnOpenKurama1.addEventListener('click', () => { window.location.href = '/chat'; });
    if (btnOpenKurama2) btnOpenKurama2.addEventListener('click', () => { window.location.href = '/chat'; });

    // =========================================================
    // AUTHENTICATION INITIALIZATION & 8-SECOND FAILSAFE TIMEOUT
    // =========================================================
    let authSettled = false;

    // Failsafe: if Supabase auth does not respond within 8 seconds, fallback to login
    const authTimeout = setTimeout(() => {
      if (!authSettled) {
        console.error("[AUTH] initialization timed out");
        authSettled = true;
        showLoginScreen();
      }
    }, 8000);

    async function initializeAuth() {
      console.log("[AUTH] initializeAuth started");

      try {
        if (!supabaseClient) {
          console.error("[AUTH] supabaseClient not initialized");
          if (!authSettled) {
            authSettled = true;
            clearTimeout(authTimeout);
            showLoginScreen();
          }
          return;
        }

        const result = await supabaseClient.auth.getSession();

        if (authSettled) return;

        const session = result.data?.session;

        if (result.error) {

          authSettled = true;
          clearTimeout(authTimeout);
          showLoginScreen();
          return;
        }

        authSettled = true;
        clearTimeout(authTimeout);

        if (session?.user) {

          showAuthenticatedWelcome(session.user);
        } else {

          showLoginScreen();
        }

        // Clean up OAuth hash fragments if any
        if (window.location.hash && (window.location.hash.includes('access_token=') || window.location.hash.includes('error='))) {
          setTimeout(() => {
            window.history.replaceState(null, '', window.location.pathname + window.location.search);
          }, 150);
        }
      } catch (err) {
        
        if (!authSettled) {
          authSettled = true;
          clearTimeout(authTimeout);
          showLoginScreen();
        }
      }
    }

    // Single onAuthStateChange listener without infinite loop
    if (supabaseClient) {
      supabaseClient.auth.onAuthStateChange((event, session) => {
        console.log("[AUTH] state change:", event);

        if (event === "SIGNED_IN" && session?.user) {
          authSettled = true;
          clearTimeout(authTimeout);
          showAuthenticatedWelcome(session.user);
        }

        if (event === "SIGNED_OUT") {
          authSettled = true;
          clearTimeout(authTimeout);
          clearAuthenticatedState();
          showLoginScreen();
        }
      });
    }

    // Trigger auth initialization immediately on page load
    initializeAuth();

    // Health check on load
    async function checkOllamaHealth() {
      try {
        const res = await fetch('/api/health');
        if (res.ok) {
          const data = await res.json();
          const statusText = document.getElementById('ollama-status-text');
          const badge = document.getElementById('ollama-status-badge');
          if (data.ollama?.online && data.ollama?.model_found) {
            if (statusText) statusText.textContent = 'OLLAMA ONLINE';
            if (badge) {
              badge.style.color = '#39FF14';
              badge.style.borderColor = 'rgba(57,255,20,0.3)';
            }
          } else {
            if (statusText) statusText.textContent = 'OLLAMA OFFLINE';
            if (badge) {
              badge.style.color = '#ff8585';
              badge.style.borderColor = 'rgba(255,85,85,0.3)';
            }
          }
        }
      } catch (_) {}
    }
    checkOllamaHealth();

    window.showToast = showToast;

    function escapeHtml(str) {
      return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }
