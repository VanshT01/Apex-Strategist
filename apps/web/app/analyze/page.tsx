import type { Metadata } from "next";
import { RaceWorkspace } from "@/components/RaceWorkspace";

export const metadata: Metadata = {
  title: "Race Analysis · Apex Strategist",
  description: "Replay and analyze historical Formula 1 races lap by lap.",
};

export default function AnalyzePage() {
  return <RaceWorkspace mode="replay" />;
}
