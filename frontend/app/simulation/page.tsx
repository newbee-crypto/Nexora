"use client";

import React from "react";

export default function SimulationPage() {
  return (
    <div className="w-full h-full relative overflow-hidden bg-zinc-50 flex-1">
      <iframe
        src="/conversio_simulation.html"
        className="absolute inset-0 w-full h-full border-0"
        title="Nexora System Architecture Simulation"
      />
    </div>
  );
}
