import type { Meta, StoryObj } from "@storybook/react";
import { Sidebar } from "./Sidebar";

const meta: Meta<typeof Sidebar> = {
  title: "Admin/Sidebar",
  component: Sidebar,
  parameters: { layout: "fullscreen" },
};
export default meta;

type Story = StoryObj<typeof Sidebar>;

/** `none` mode: no user, no Sign out. */
export const Default: Story = {
  render: () => (
    <div className="h-[480px]">
      <Sidebar />
    </div>
  ),
};

/** `oidc` mode: the signed-in principal and Sign out. */
export const SignedIn: Story = {
  render: () => (
    <div className="h-[480px]">
      <Sidebar user={{ principal: "alice", roles: ["admin", "reader"] }} />
    </div>
  ),
};
