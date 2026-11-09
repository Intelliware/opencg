import type { Preview } from "@storybook/react";
import React, { useEffect } from "react";
import "../src/app/globals.css";

// Capitalised: Storybook renders decorators inside a React render, so hooks
// are valid here; the name tells eslint-plugin-react-hooks the same.
const WithTheme = (Story: React.ComponentType, context: { globals: { theme?: string } }) => {
  const theme = context.globals.theme ?? "light";
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
  return (
    <div className="bg-background p-4 text-foreground">
      <Story />
    </div>
  );
};

const preview: Preview = {
  parameters: {
    controls: { expanded: true },
  },
  globalTypes: {
    theme: {
      description: "Color theme",
      toolbar: {
        title: "Theme",
        icon: "mirror",
        items: ["light", "dark"],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: "light" },
  decorators: [WithTheme],
};

export default preview;
