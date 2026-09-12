import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "@dashboard/index.css";
import "@dashboard/styles/tokens.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
