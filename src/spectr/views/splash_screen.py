from textual import events
from textual.screen import Screen
from textual.widgets import Static

GHOST = """
                                                             ..:::.                                 
                                                     .:::::::      :::::::.                         
                                                 .::::.                  .::::                      
                                               :::                           .:::                   
                                             :::                                :::                 
                                           :::                                    .::               
                                         .::                   :::::::              :::             
                                        .:.                          :::              ::            
                                       .::                        :::: ::              ::           
                                      .::                        ::::::              :::            
                                      ::                         ::::::           :::               
                                     ::                          ::::::         :::                 
                   :::::::::::::::  ::                            ::::       :::                    
                                    ::                                     ::                       
                                    ::                                  :::                         
          ::::::::::::::::::::::   ::                                :::                           
                                   ::                             .:::                              
                                  ::                             ::                                
              ::::::::::::::::    ::      .                        :::                              
                                 ::       :                          :::                            
                                ::       :                              :::                         
                              .::       :                                  :::                      
                             ::.      ::                                     :::.                   
                          .:::      .:.                                         :::                 
                      .::::.      .::                 :                            ::               
              ::::::::.         ::.                  :.                            ::               
               ::.          .::                     :.                            ::                
                .::                                :.                ..          ::                 
                   :::                           ::                  :         .:.                  
                      :::::::::                .:.                 .:         ::.                   
                              ::              ::                  ::        .::                     
                              .:.           ::                   ::        ::.                      
                             .::         ::.                    :.       :::                        
                            ::.                               ::        ::                          
                           ::              .::::::          .:        ::                            
                           ::       ..:::::      ::       .:       .::.                             
                             ::::::::            ::              :::.                               
                                                ::            .:::                                  
                                               ::::::::::::::::                                     
"""

ASCII_HEIGHT = len(GHOST.strip("\n").splitlines())

class SplashScreen(Screen):
    """Center-screen logo while data initialises."""

    FALLBACK_TEXT = "SPECTR"

    def compose(self):
        self.logo = Static(id="logo-art", classes="center")
        yield self.logo

    def on_mount(self) -> None:
        self._update_logo()

    def on_resize(self, event: events.Resize) -> None:  # noqa: D401
        self._update_logo()

    def _update_logo(self) -> None:
        if self.app.size.height < ASCII_HEIGHT:
            self.logo.update(self.FALLBACK_TEXT)
        else:
            self.logo.update(GHOST)