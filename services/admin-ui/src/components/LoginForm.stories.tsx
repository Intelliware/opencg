import type { Meta, StoryObj } from "@storybook/react";
import { LoginForm } from "./LoginForm";

const meta: Meta<typeof LoginForm> = {
  title: "Admin/LoginForm",
  component: LoginForm,
  args: { next: "/graph" },
};
export default meta;

type Story = StoryObj<typeof LoginForm>;

export const Default: Story = {};

export const IncorrectPassword: Story = {
  args: { error: true },
};
