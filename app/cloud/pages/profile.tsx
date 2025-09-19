import { useUser } from '@clerk/clerk-react';
import {
  Avatar,
  Box,
  Card,
  CardContent,
  Chip,
  Container,
  Link,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { CreateNewTenant } from '../components/CreateNewTenant';
import { SoftwareAutomationQuestion } from '../components/SoftwareAutomationQuestion';

export default function ProfilePage() {
  const { user, isLoaded } = useUser();
  const [softwareToAutomate, setSoftwareToAutomate] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [showHello, setShowHello] = useState(
    Boolean((user as any)?.unsafeMetadata?.softwareToAutomate),
  );

  const name = user?.fullName || user?.username;

  const handleSaveAutomationSoftware = async () => {
    if (!user) return;
    if (!softwareToAutomate.trim()) return;

    try {
      setIsSaving(true);
      await user.update({
        unsafeMetadata: {
          ...(user as any).unsafeMetadata,
          softwareToAutomate: softwareToAutomate.trim(),
        },
      });
      setShowHello(true);
    } finally {
      setIsSaving(false);
    }
  };

  useEffect(() => {
    // Reflect saved answer from user metadata
    setShowHello(Boolean((user as any)?.unsafeMetadata?.softwareToAutomate));
    const existing = (user as any)?.unsafeMetadata?.softwareToAutomate as string | undefined;
    if (existing) {
      setSoftwareToAutomate(existing);
    }
  }, [user]);

  if (!isLoaded) {
    return (
      <Box
        sx={{
          minHeight: '100vh',
          background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Typography>Loading...</Typography>
      </Box>
    );
  }

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
      <Container maxWidth="md">
        {!showHello ? (
          <Card
            sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              width: 'auto',
              boxShadow: '0 10px 40px rgba(0,0,0,0.12)',
              borderRadius: 3,
              p: 10,
            }}
          >
            <CardContent sx={{ p: { xs: 3, sm: 5 } }}>
              <Stack spacing={3}>
                <Stack alignItems="center" spacing={1}>
                  <Box
                    component="img"
                    src="/logo-white.svg"
                    alt="legacy-use logo"
                    sx={{ height: 56, width: 'auto', filter: 'brightness(0.1)' }}
                  />
                  <Typography variant="h5">Let's get you set up</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center' }}>
                    Answer one quick question so we can tailor your experience.
                  </Typography>
                </Stack>

                <SoftwareAutomationQuestion
                  value={softwareToAutomate}
                  onValueChange={value => setSoftwareToAutomate(value)}
                  onSave={handleSaveAutomationSoftware}
                  isSaving={isSaving}
                />
              </Stack>
            </CardContent>
          </Card>
        ) : (
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <Card
              sx={{
                maxWidth: 600,
                width: '100%',
                boxShadow: '0 8px 32px rgba(0,0,0,0.1)',
                borderRadius: 3,
              }}
            >
              <CardContent sx={{ p: 4, textAlign: 'center' }}>
                <Stack spacing={3} alignItems="center">
                  {/* Logo */}
                  <Box
                    component="img"
                    src="/logo-white.svg"
                    alt="legacy-use logo"
                    sx={{
                      height: 80,
                      width: 'auto',
                      filter: 'brightness(0.1)',
                    }}
                  />

                  {/* Welcome Message */}
                  <Typography variant="h3" component="h1" gutterBottom>
                    Hello, legacy-use!
                  </Typography>

                  {/* User Information */}
                  {user && (
                    <Box>
                      <Stack spacing={2} alignItems="center">
                        <Avatar
                          src={user.imageUrl}
                          alt={user.fullName || user.username || 'User'}
                          sx={{
                            width: 80,
                            height: 80,
                            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                          }}
                        />

                        <Stack spacing={1} alignItems="center">
                          {name && <Typography variant="h5">{name}</Typography>}

                          {user.primaryEmailAddress && (
                            <Typography variant="body1" color="text.secondary">
                              {user.primaryEmailAddress.emailAddress}
                            </Typography>
                          )}

                          {user.createdAt && (
                            <Chip
                              label={`Member since ${new Date(user.createdAt).toLocaleDateString()}`}
                              variant="outlined"
                              size="small"
                            />
                          )}
                        </Stack>
                      </Stack>
                    </Box>
                  )}

                  <Typography variant="body1">
                    You're all set, we will send you an email with your credentials shortly.
                  </Typography>

                  {/* Description */}
                  <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 400 }}>
                    Start automating work in your desktop applications and expose workflows as
                    modern APIs with our reliable AI agents.
                  </Typography>
                </Stack>
              </CardContent>
            </Card>

            <CreateNewTenant />

            {/* Additional Info */}
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center' }}>
              Check out our <Link href="https://legacy-use.github.io/docs/">documentation</Link> or
              contact our <Link href="mailto:automate@legacy-use.com">support team</Link>.
            </Typography>
          </Box>
        )}
      </Container>
    </Box>
  );
}
