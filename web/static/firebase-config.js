// Configuracion Firebase compartida por login.html, register.html e index.html
// Se carga desde CDN (firebase v10 modular).
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.13.2/firebase-app.js";
import {
  getAuth,
  setPersistence,
  browserLocalPersistence,
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile,
  onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.13.2/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyA5Mn4fETGk1Iw3X1CfMWdn7bbvnj1iqYM",
  authDomain: "upao-proyects.firebaseapp.com",
  projectId: "upao-proyects",
  storageBucket: "upao-proyects.firebasestorage.app",
  messagingSenderId: "877165514263",
  appId: "1:877165514263:web:2d3b11232472c0b3585652",
  measurementId: "G-375DFD01YJ",
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
// Mantiene la sesion al refrescar el navegador.
setPersistence(auth, browserLocalPersistence).catch(() => {});

const googleProvider = new GoogleAuthProvider();

// ---- Helpers reusables --------------------------------------------------
async function syncWithBackend(user, displayNameOverride) {
  const idToken = await user.getIdToken();
  const resp = await fetch("/api/auth/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id_token: idToken,
      display_name: displayNameOverride || user.displayName || null,
    }),
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error("Backend rechazo el token: " + detail);
  }
  const profile = await resp.json();
  // Cache local del perfil para la tienda.
  localStorage.setItem("aura_id_token", idToken);
  localStorage.setItem("aura_user", JSON.stringify(profile));
  return profile;
}

function mapFirebaseError(err) {
  const code = err && err.code ? err.code : "";
  const map = {
    "auth/invalid-email": "El correo no es valido.",
    "auth/user-not-found": "No existe una cuenta con ese correo.",
    "auth/wrong-password": "Contrasena incorrecta.",
    "auth/invalid-credential": "Credenciales invalidas.",
    "auth/email-already-in-use": "Ese correo ya esta registrado. Intenta iniciar sesion.",
    "auth/weak-password": "La contrasena debe tener al menos 6 caracteres.",
    "auth/popup-closed-by-user": "Cerraste la ventana de Google antes de terminar.",
    "auth/network-request-failed": "Sin conexion. Revisa tu internet.",
    "auth/too-many-requests": "Demasiados intentos. Espera un momento.",
  };
  return map[code] || (err && err.message) || "Ocurrio un error inesperado.";
}

export {
  auth,
  googleProvider,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile,
  onAuthStateChanged,
  syncWithBackend,
  mapFirebaseError,
};
