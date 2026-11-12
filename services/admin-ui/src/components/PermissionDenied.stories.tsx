import type { Meta, StoryObj } from "@storybook/react";
import { PermissionDenied } from "./PermissionDenied";

const meta: Meta<typeof PermissionDenied> = {
  title: "Admin/PermissionDenied",
  component: PermissionDenied,
};
export default meta;

type Story = StoryObj<typeof PermissionDenied>;

export const Tombstone: Story = { args: { action: "tombstone this entity" } };
export const IngestionRun: Story = { args: { action: "start an ingestion run" } };
export const PageView: Story = {
  args: { action: "view this page", detail: "Your account has no openCG role." },
};
