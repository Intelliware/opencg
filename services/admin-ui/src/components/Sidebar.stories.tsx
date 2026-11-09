import type { Meta, StoryObj } from "@storybook/react";
import { Sidebar } from "./Sidebar";

const meta: Meta<typeof Sidebar> = {
  title: "Admin/Sidebar",
  component: Sidebar,
  parameters: { layout: "fullscreen" },
};
export default meta;

type Story = StoryObj<typeof Sidebar>;

export const Default: Story = {
  render: () => (
    <div className="h-[480px]">
      <Sidebar />
    </div>
  ),
};

export const WithSignOut: Story = {
  render: () => (
    <div className="h-[480px]">
      <Sidebar signOut />
    </div>
  ),
};
