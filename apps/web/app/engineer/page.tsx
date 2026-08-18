import type { Metadata } from "next";
import { RaceWorkspace } from "@/components/RaceWorkspace";

export const metadata: Metadata = {
  title: "Race Engineer · Apex Strategist",
  description: "Take control of Formula 1 strategy one lap at a time.",
};

export default function EngineerPage() {
  return <RaceWorkspace mode="engineer" />;
}
