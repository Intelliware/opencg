import type { Meta, StoryObj } from "@storybook/react";
import { UnauthenticatedBanner } from "./UnauthenticatedBanner";

const meta: Meta<typeof UnauthenticatedBanner> = {
  title: "Admin/UnauthenticatedBanner",
  component: UnauthenticatedBanner,
};
export default meta;

type Story = StoryObj<typeof UnauthenticatedBanner>;

export const Default: Story = {};
