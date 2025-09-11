import * as Clerk from '@clerk/elements/common';
import * as SignUp from '@clerk/elements/sign-up';
import { Box, Container, Stack, Typography } from '@mui/material';

export default function SignupPage() {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        py: 4,
      }}
    >
      <Container maxWidth="lg">
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            minHeight: '100vh',
            '@media (max-width: 900px)': {
              flexDirection: 'column',
              gap: 4,
              textAlign: 'center',
            },
          }}
        >
          {/* Left side - Clerk form */}
          <Box>
            <SignUp.Root>
              <SignUp.Step name="start">
                <Clerk.Connection name="google">Sign up with Google</Clerk.Connection>

                <Clerk.Field name="emailAddress">
                  <Clerk.Label>Email</Clerk.Label>
                  <Clerk.Input />
                  <Clerk.FieldError />
                </Clerk.Field>

                <Clerk.Field name="password">
                  <Clerk.Label>Password</Clerk.Label>
                  <Clerk.Input />
                  <Clerk.FieldError />
                </Clerk.Field>

                <Clerk.Field name="unsafeMetadata.softwareToAutomate">
                  <Clerk.Label>What software do you want to automate?</Clerk.Label>
                  <Clerk.Input />
                  <Clerk.FieldError />
                </Clerk.Field>

                <SignUp.Action submit>Sign up</SignUp.Action>
              </SignUp.Step>

              <SignUp.Step name="verifications">
                <SignUp.Strategy name="email_code">
                  <Clerk.Field name="code">
                    <Clerk.Label>Email Code</Clerk.Label>
                    <Clerk.Input />
                    <Clerk.FieldError />
                  </Clerk.Field>

                  <SignUp.Action submit>Verify</SignUp.Action>
                </SignUp.Strategy>
              </SignUp.Step>
            </SignUp.Root>
          </Box>

          {/* Right side - Marketing text */}
          <Box
            sx={{
              flex: 1,
              maxWidth: '500px',
              '@media (max-width: 900px)': {
                maxWidth: '100%',
              },
            }}
          >
            <Stack spacing={2}>
              <Box
                component="img"
                src="/logo-white.svg"
                alt="legacy-use logo"
                sx={{
                  height: 100,
                  width: 'auto',
                  filter: 'brightness(0.1)',
                  alignSelf: 'flex-start',
                }}
              />
              <Typography variant="h2">Hello, legacy-use</Typography>
              <Typography variant="subtitle1">
                Automate work in your desktop applications and expose workflows as modern APIs. Our
                reliable AI agents interact with software like your human coworkers.
              </Typography>
            </Stack>
          </Box>
        </Box>
      </Container>
    </Box>
  );
}
