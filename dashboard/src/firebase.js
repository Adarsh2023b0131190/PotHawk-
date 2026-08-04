import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyBkVmqI1DizkvfZ4Nv-4PHv1orio5krQMc",
  authDomain: "pothowk.firebaseapp.com",
  projectId: "pothowk",
  storageBucket: "pothowk.firebasestorage.app",
  messagingSenderId: "636412044133",
  appId: "1:636412044133:web:91c799daa11c0e6118f78c"
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);