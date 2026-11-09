import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { Providers } from "@/app/providers";
import { AppRoutes } from "@/app/routes";
import "./index.css";

const container = document.getElementById("root");
if (!container) throw new Error("The #root element is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <Providers>
        <AppRoutes />
      </Providers>
    </BrowserRouter>
  </StrictMode>,
);
