import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, HashRouter } from "react-router-dom";
import { SINGLE } from "./routing.js";
import App from "./App.jsx";
import "./styles.css";
import "./redesign.css";

const Router = SINGLE ? HashRouter : BrowserRouter;

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Router>
      <App />
    </Router>
  </StrictMode>,
);
