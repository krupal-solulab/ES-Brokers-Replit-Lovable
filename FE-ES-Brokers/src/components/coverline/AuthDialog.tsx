import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from "@/components/ui/form";
import { PasswordStrengthMeter } from "./PasswordStrengthMeter";
import { simulateRequest } from "@/lib/simulate";
import { login } from "@/lib/api/auth";

type Mode = "login" | "signup";
type Status = "idle" | "loading" | "success" | "error";

const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});
type LoginValues = z.infer<typeof loginSchema>;

const passwordSchema = z
  .string()
  .min(8, "At least 8 characters")
  .refine((v) => /[a-z]/.test(v) && /[A-Z]/.test(v), "Use upper and lowercase letters")
  .refine((v) => /\d/.test(v), "Include at least one number");

const signupSchema = z
  .object({
    name: z.string().min(2, "Enter your full name"),
    email: z.string().min(1, "Email is required").email("Enter a valid email address"),
    password: passwordSchema,
    confirmPassword: z.string().min(1, "Confirm your password"),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });
type SignupValues = z.infer<typeof signupSchema>;

export function AuthDialog({
  open,
  onOpenChange,
  mode,
  onModeChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: Mode;
  onModeChange: (mode: Mode) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-0 overflow-hidden rounded-none p-0 sm:max-w-md">
        {mode === "login" ? (
          <LoginForm onSwitch={() => onModeChange("signup")} onDone={() => onOpenChange(false)} />
        ) : (
          <SignupForm onSwitch={() => onModeChange("login")} onDone={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function StatusBanner({ status, successLabel }: { status: Status; successLabel: string }) {
  if (status === "success") {
    return (
      <div className="flex items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
        <CheckCircle2 className="h-4 w-4 shrink-0" />
        {successLabel}
      </div>
    );
  }
  return null;
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      {message}
    </div>
  );
}

function LoginForm({ onSwitch, onDone }: { onSwitch: () => void; onDone: () => void }) {
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const navigate = useNavigate();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  async function onSubmit(values: LoginValues) {
    setStatus("loading");
    setErrorMsg("");
    try {
      // Real email -> role lookup (core/auth/router.py). Still no real
      // password check — the password field stays required for the
      // existing UX, but only the email determines who you're logged in
      // as; see identity.ts for how that's stored per browser tab/window.
      await login(values.email);
      setStatus("success");
      setTimeout(() => {
        onDone();
        navigate({ to: "/app" });
      }, 700);
    } catch (err) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <div className="p-6">
      <DialogHeader>
        <DialogTitle className="font-serif text-2xl">Log in to Coverline</DialogTitle>
        <DialogDescription>
          Welcome back — pick up your placement queue where you left off.
        </DialogDescription>
      </DialogHeader>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="mt-5 space-y-4" noValidate>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Work email</FormLabel>
                <FormControl>
                  <Input
                    type="email"
                    autoComplete="email"
                    placeholder="you@agency.com"
                    disabled={status === "loading"}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel>Password</FormLabel>
                  <button
                    type="button"
                    className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm"
                  >
                    Forgot password?
                  </button>
                </div>
                <FormControl>
                  <Input
                    type="password"
                    autoComplete="current-password"
                    disabled={status === "loading"}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {status === "error" && <ErrorBanner message={errorMsg} />}
          <StatusBanner status={status} successLabel="Logged in — redirecting…" />

          <Button
            type="submit"
            variant="brand"
            className="w-full justify-center"
            disabled={status === "loading" || status === "success"}
            aria-busy={status === "loading"}
          >
            {status === "loading" && <Loader2 className="h-4 w-4 animate-spin" />}
            {status === "loading" ? "Logging in…" : "Log in"}
          </Button>
        </form>
      </Form>

      <p className="mt-5 text-center text-sm text-muted-foreground">
        New to Coverline?{" "}
        <button
          type="button"
          onClick={onSwitch}
          className="font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm"
        >
          Create an account
        </button>
      </p>
    </div>
  );
}

function SignupForm({ onSwitch, onDone }: { onSwitch: () => void; onDone: () => void }) {
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const navigate = useNavigate();
  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: { name: "", email: "", password: "", confirmPassword: "" },
  });
  const password = form.watch("password");

  async function onSubmit(values: SignupValues) {
    setStatus("loading");
    setErrorMsg("");
    try {
      // TODO: replace with a real signup call (e.g. Supabase Auth signUp) and
      // a real DB write. Nothing here creates a persisted account yet.
      await simulateRequest({ email: values.email });
      setStatus("success");
      setTimeout(() => {
        onDone();
        navigate({ to: "/app" });
      }, 900);
    } catch (err) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <div className="p-6">
      <DialogHeader>
        <DialogTitle className="font-serif text-2xl">Create your account</DialogTitle>
        <DialogDescription>Set up Coverline for your placement team.</DialogDescription>
      </DialogHeader>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="mt-5 space-y-4" noValidate>
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Full name</FormLabel>
                <FormControl>
                  <Input
                    autoComplete="name"
                    placeholder="Sam Delgado"
                    disabled={status === "loading"}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Work email</FormLabel>
                <FormControl>
                  <Input
                    type="email"
                    autoComplete="email"
                    placeholder="you@agency.com"
                    disabled={status === "loading"}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    autoComplete="new-password"
                    disabled={status === "loading"}
                    {...field}
                  />
                </FormControl>
                <PasswordStrengthMeter password={password} />
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="confirmPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Confirm password</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    autoComplete="new-password"
                    disabled={status === "loading"}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {status === "error" && <ErrorBanner message={errorMsg} />}
          <StatusBanner status={status} successLabel="Account created — redirecting…" />

          <Button
            type="submit"
            variant="brand"
            className="w-full justify-center"
            disabled={status === "loading" || status === "success"}
            aria-busy={status === "loading"}
          >
            {status === "loading" && <Loader2 className="h-4 w-4 animate-spin" />}
            {status === "loading" ? "Creating account…" : "Create account"}
          </Button>
        </form>
      </Form>

      <p className="mt-5 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <button
          type="button"
          onClick={onSwitch}
          className="font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm"
        >
          Log in
        </button>
      </p>
    </div>
  );
}
