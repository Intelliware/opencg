import type { Meta, StoryObj } from "@storybook/react";
import { UserBadge } from "./UserBadge";

const meta: Meta<typeof UserBadge> = {
  title: "Admin/UserBadge",
  component: UserBadge,
  decorators: [(Story) => <div className="w-48"><Story /></div>],
};
export default meta;

type Story = StoryObj<typeof UserBadge>;

export const Admin: Story = { args: { principal: "alice", roles: ["admin", "reader"] } };
export const Reader: Story = { args: { principal: "bob", roles: ["reader"] } };
export const NoRoles: Story = { args: { principal: "carol", roles: [] } };
export const LongName: Story = {
  args: { principal: "service-account-opencg-smoke-legal", roles: ["legal", "reader", "auditor"] },
};
