import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import Home from "@/app/page";
import { SiteHeader } from "@/components/SiteHeader";

const usePathname = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => usePathname(),
}));

beforeEach(() => {
  usePathname.mockReturnValue("/analyze");
});

test("global navigation exposes separate analysis and engineer pages", () => {
  render(<SiteHeader />);

  const analysis = screen.getByRole("link", { name: /race analysis/i });
  const engineer = screen.getByRole("link", { name: /race engineer/i });
  expect(analysis).toHaveAttribute("href", "/analyze");
  expect(analysis).toHaveAttribute("aria-current", "page");
  expect(engineer).toHaveAttribute("href", "/engineer");
  expect(engineer).not.toHaveAttribute("aria-current");
  expect(
    screen.queryByLabelText("Timing database online"),
  ).not.toBeInTheDocument();
});

test("home navigation omits the internal data status", () => {
  usePathname.mockReturnValue("/");
  render(<SiteHeader />);

  expect(
    screen.queryByLabelText("Timing database online"),
  ).not.toBeInTheDocument();
});

test("home page offers both F1 experiences directly", () => {
  render(<Home />);

  expect(
    screen.getByRole("link", { name: /enter race engineer/i }),
  ).toHaveAttribute("href", "/engineer");
  expect(
    screen.getAllByRole("link", { name: /analyze past races/i })[0],
  ).toHaveAttribute("href", "/analyze");
  expect(screen.getByText("ENGINEER THE RACE")).toBeInTheDocument();
  expect(screen.getByText("ANALYZE THE PAST")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /vansh talreja/i })).toHaveAttribute(
    "href",
    "https://github.com/VanshT01",
  );
});
